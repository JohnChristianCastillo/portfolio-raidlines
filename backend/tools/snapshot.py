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

from app.config import settings  # noqa: E402
from app.services import catalog, timeline  # noqa: E402
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

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "zone": {
            "id": zone["id"],
            "name": zone["name"],
            "expansion": zone["expansion"],
            "encounters": zone["encounters"],
        },
        "difficulties": [
            d for d in catalog.DIFFICULTIES if d["id"] in args.difficulties
        ],
        "specs": [
            {
                "key": spec.key,
                "label": spec.label,
                "specId": spec.spec_id,
                "role": spec.role,
                "className": spec.class_name,
                "groups": [
                    {"key": g.key, "label": g.label, "color": g.color}
                    for g in spec.groups
                ],
            }
            for spec in (SPECS[k] for k in spec_keys)
        ],
        "topN": settings.top_n,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    total = sum(p.stat().st_size for p in out.rglob("*.json"))
    minutes = (time.time() - started) / 60
    print(
        f"\n{written} written, {skipped} skipped, {failed} failed in {minutes:.1f} min"
    )
    print(f"{total / 1024 / 1024:.1f} MB under {out}")
    print(f"manifest: {out / 'manifest.json'}")


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
