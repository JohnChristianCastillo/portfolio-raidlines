"""Precompute every board as static JSON, for a site that calls no API at all.

    python tools/snapshot.py                      # current tier, heroic + mythic
    python tools/snapshot.py --difficulties 5     # mythic only
    python tools/snapshot.py --spec rogue-subtlety
    python tools/snapshot.py --force              # rebuild boards already written

Writes one file per board plus a manifest:

    <out>/manifest.json
    <out>/<spec>/<encounter>-<difficulty>.json

Three properties matter here, and each earns its complexity.

Paced. The Warcraft Logs budget is 3600 points an hour, and a cold board costs
roughly a hundred. Rather than model that, the real budget is read from the API
between boards and the run sleeps when it gets low. Modelling drifts; asking does
not, and the check costs a point or two an hour.

Resumable. A board already on disk is skipped unless --force. A laptop that sleeps
mid-run therefore costs nothing: start it again and it carries on. The response
cache underneath means even a forced rebuild of an unchanged fight is free.

Self-contained. Talents are baked into each board rather than fetched on demand,
because on a static site there is no demand to fetch on. That is the one place this
costs materially more than serving live: one extra query per player.

Boss timelines are written once per encounter and difficulty to <out>/bosses/, not
once per board. A boss behaves the same whoever is looking at it, so a tier is
eighteen of them rather than one for each of the hundreds of boards.

Tooltip text is written once to <out>/spells.json rather than repeated in every
board. The same forty abilities appear on every board of a spec, and inlining their
descriptions would have cost more than the boards themselves.
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.blizzard import BlizzardError, Client  # noqa: E402
from app.config import settings  # noqa: E402
from app.services import bosses, catalog, descriptions, timeline  # noqa: E402
from app.spells import SPECS  # noqa: E402
from app.wcl import client  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "data"

# Stop and wait below this many points. A cold board costs about a hundred, so this
# leaves room for one to finish rather than dying halfway through.
LOW_WATER = 250


class Budget:
    """Keeps the run inside the hourly point allowance."""

    def __init__(self, low_water: int = LOW_WATER) -> None:
        self.low_water = low_water
        self.spent_at_start: float | None = None

    async def wait_if_low(self) -> dict:
        info = await client.rate_limit()
        limit = float(info.get("limitPerHour") or 3600)
        spent = float(info.get("pointsSpentThisHour") or 0)
        remaining = limit - spent
        if self.spent_at_start is None:
            self.spent_at_start = spent

        if remaining < self.low_water:
            resets_in = int(info.get("pointsResetIn") or 300) + 15
            print(
                f"  budget down to {remaining:.0f} points, sleeping {resets_in}s "
                "for the hourly reset"
            )
            await asyncio.sleep(resets_in)
            info = await client.rate_limit()
        return info


async def board(
    encounter: dict, difficulty: int, spec_key: str, with_talents: bool
) -> dict:
    data = await timeline.build(encounter["id"], difficulty, spec_key)

    if with_talents:
        # A static page cannot ask for these later, so they ride along now. Cached
        # like any fight, so a rebuild does not pay again.
        for player in data["players"]:
            actor = player.get("actorId")
            if actor is None:
                player["talents"] = ""
                continue
            try:
                player["talents"] = await timeline.talents(
                    player["reportCode"], player["fightId"], actor
                )
            except (client.WclError, ValueError) as exc:
                # One missing loadout should not cost the board.
                print(f"    ({player['name']}: no talents, {exc})")
                player["talents"] = ""
    return data


async def run(args) -> None:
    out = Path(args.out)
    zones = await catalog.zones()
    if not zones:
        raise SystemExit("no raid zones returned")

    zone = zones[0] if args.zone is None else next(
        (z for z in zones if z["id"] == args.zone), None
    )
    if zone is None:
        raise SystemExit(f"zone {args.zone} not found")

    spec_keys = [args.spec] if args.spec else list(SPECS)
    for key in spec_keys:
        if key not in SPECS:
            raise SystemExit(f"unknown spec {key!r}")

    jobs = [
        (encounter, difficulty, key)
        for key in spec_keys
        for encounter in zone["encounters"]
        for difficulty in args.difficulties
    ]
    print(
        f"{zone['name']}: {len(zone['encounters'])} bosses x "
        f"{len(args.difficulties)} difficulties x {len(spec_keys)} specs "
        f"= {len(jobs)} boards\n"
    )

    budget = Budget()
    written = skipped = failed = 0
    started = time.time()

    for index, (encounter, difficulty, key) in enumerate(jobs, start=1):
        target = out / key / f"{encounter['id']}-{difficulty}.json"
        label = f"[{index}/{len(jobs)}] {key} {encounter['name']} d{difficulty}"

        if target.is_file() and not args.force:
            skipped += 1
            continue

        info = await budget.wait_if_low()
        remaining = float(info.get("limitPerHour") or 3600) - float(
            info.get("pointsSpentThisHour") or 0
        )
        try:
            data = await board(encounter, difficulty, key, not args.no_talents)
        except (client.WclError, ValueError) as exc:
            print(f"{label}: FAILED {exc}")
            failed += 1
            continue

        # An empty board is still written. Early in a tier most bosses have no
        # ranked parses yet, and a present-but-empty file lets the UI say so instead
        # of looking broken. A later run overwrites it once parses appear.
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        written += 1
        count = len(data["players"])
        print(
            f"{label}: {count if count else 'no'} parses, "
            f"{target.stat().st_size / 1024:.0f} KB, {remaining:.0f} points left"
        )

    await write_boss_timelines(out, zone, args.difficulties, spec_keys[0])

    write_descriptions(out)

    # The manifest describes what is on disk, not what this run asked for. Runs are
    # commonly partial (one spec, one difficulty, or resumed after a sleep), and a
    # manifest built from argv would quietly drop every board an earlier run wrote.
    present: dict[str, set[int]] = {}
    for spec_dir in sorted(p for p in out.iterdir() if p.is_dir()):
        for board_file in spec_dir.glob("*-*.json"):
            try:
                _, diff = board_file.stem.rsplit("-", 1)
                present.setdefault(spec_dir.name, set()).add(int(diff))
            except ValueError:
                continue

    covered_specs = [k for k in SPECS if k in present]
    covered_difficulties = sorted({d for diffs in present.values() for d in diffs})

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "zone": {
            "id": zone["id"],
            "name": zone["name"],
            "expansion": zone["expansion"],
            "encounters": zone["encounters"],
        },
        "difficulties": [
            d for d in catalog.DIFFICULTIES if d["id"] in covered_difficulties
        ],
        "specs": [
            {
                "key": spec.key,
                "label": spec.label,
                "specId": spec.spec_id,
                "role": spec.role,
                "className": spec.class_name,
                "classKey": spec.class_key,
                "groups": [
                    {"key": g.key, "label": g.label, "color": g.color}
                    for g in spec.groups
                ],
            }
            for spec in (SPECS[k] for k in covered_specs)
        ],
        "topN": settings.top_n,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"\nmanifest covers {len(covered_specs)} specs, difficulties "
        f"{covered_difficulties}"
    )

    total = sum(p.stat().st_size for p in out.rglob("*.json"))
    minutes = (time.time() - started) / 60
    print(
        f"\n{written} written, {skipped} skipped, {failed} failed in {minutes:.1f} min"
    )
    print(f"{total / 1024 / 1024:.1f} MB under {out}")
    print(f"manifest: {out / 'manifest.json'}")


async def write_boss_timelines(
    out: Path, zone: dict, difficulties: list[int], spec_key: str
) -> None:
    """One boss timeline per encounter and difficulty, shared by every spec.

    The spec argument only picks which rankings to pull sample pulls from; the boss
    does the same thing regardless of who is watching.
    """
    print("\nboss timelines")
    for encounter in zone["encounters"]:
        for difficulty in difficulties:
            target = out / "bosses" / f"{encounter['id']}-{difficulty}.json"
            label = f"  {encounter['name'][:26]:<26} d{difficulty}"
            try:
                refs = await timeline.references(encounter["id"], difficulty, spec_key)
                data = await bosses.build(encounter["id"], difficulty, refs)
            except (client.WclError, ValueError) as exc:
                print(f"{label}: FAILED {exc}")
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            print(
                f"{label}: {len(data['abilities'])} abilities, "
                f"{len(data['casts'])} casts, from {data['samples']} pulls"
            )


def write_descriptions(out: Path) -> None:
    """Collect every spell and trinket on the boards, and look up their tooltips.

    Driven by what the boards actually reference rather than by the catalog, so
    discovered trinkets and potions are included without being listed anywhere.
    """
    if not settings.blizzard_enabled:
        print("\nno Blizzard credentials, skipping tooltips")
        return

    spell_ids: set[int] = set()
    item_ids: set[int] = set()
    for board_file in out.rglob("*-*.json"):
        try:
            data = json.loads(board_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for group in data.get("groups") or []:
            for spell in group.get("spells") or []:
                identifier = spell.get("id", 0)
                # Trinket toggles live in negative ID space, keyed by item.
                (item_ids if identifier < 0 else spell_ids).add(abs(identifier))

    print(f"\ntooltips for {len(spell_ids)} spells and {len(item_ids)} items")
    try:
        with Client() as blizzard:
            entries = descriptions.for_spells(blizzard, spell_ids)
            entries.update(descriptions.for_items(blizzard, item_ids))
    except BlizzardError as exc:
        print(f"  skipped: {exc}")
        return

    (out / "spells.json").write_text(
        json.dumps(entries, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    missing = len(spell_ids) + len(item_ids) - len(entries)
    print(
        f"  {len(entries)} described, {missing} without text "
        "(potions are item effects Blizzard does not expose)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--zone", type=int, help="zone ID; default is the current tier")
    parser.add_argument("--spec", help="one spec key; default is all of them")
    parser.add_argument(
        "--difficulties",
        type=int,
        nargs="+",
        default=[4, 5],
        # Normal is excluded by default: nobody copies cooldown usage off a Normal
        # parse, and it is a third of the work.
        help="difficulty IDs, default heroic and mythic",
    )
    parser.add_argument("--force", action="store_true", help="rewrite existing boards")
    parser.add_argument(
        "--no-talents", action="store_true", help="skip the per-player loadout strings"
    )
    args = parser.parse_args()

    if not settings.live_enabled:
        raise SystemExit("no Warcraft Logs credentials configured")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
