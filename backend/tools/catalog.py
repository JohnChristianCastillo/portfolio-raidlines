"""Turn a list of ability names into verified catalog entries.

    python tools/catalog.py --class "Death Knight" --spec Frost --encounter 3470 \
        --names "Death's Advance" "Anti-Magic Shell" "Pillar of Frost"

    python tools/catalog.py --class Rogue --spec Subtlety --encounter 3470 \
        --names-file names.txt

The problem this solves: a catalog needs spell IDs, and a spell ID typed from memory
that is subtly wrong does not error. It silently matches nothing, and the toggle
draws an empty row forever. Blizzard's spell search cannot be used to look them up
either, since its exact-name search returns nothing even for spells that plainly
exist.

So the IDs are read out of real logs. For the top parses of a spec, every ability
cast or buff applied is collected, and the requested names are matched against what
those players actually did. That verifies three things at once: the ID is right, the
ability still exists in this patch, and players of this spec genuinely use it.

Buffs are collected as well as casts because a good few tracked abilities never
appear as a cast: some are procs, some are applied by an item, and some are the buff
half of a talent. Casts are preferred when a name appears as both.

Names that match nothing are reported rather than guessed at. Usually that means a
typo, an ability renamed in this patch, or one that nobody in the top parses took.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.config import settings  # noqa: E402
from app.wcl import client, queries  # noqa: E402

EVENTS = """
query Abilities($code: String!, $fightId: Int!, $filter: String!, $type: EventDataType!) {
  reportData {
    report(code: $code) {
      masterData { abilities { gameID name icon } }
      events(
        fightIDs: [$fightId]
        dataType: $type
        filterExpression: $filter
        limit: 3000
      ) { data }
    }
  }
}
"""


def normalise(name: str) -> str:
    """Match loosely enough to survive hand-typed lists.

    Case, punctuation and spacing all vary in practice: "Deaths' Advance" for
    "Death's Advance", "Pillar or frost" for "Pillar of Frost". Stripping everything
    but letters and digits absorbs the first two. The third is a real typo and is
    reported rather than guessed.
    """
    return "".join(ch for ch in name.lower() if ch.isalnum())


async def collect(encounter: int, difficulty: int, class_name: str, spec_name: str,
                  metric: str, top: int) -> dict[str, tuple[int, str, str]]:
    """Every ability the top parses cast or gained, keyed by normalised name."""
    data = await client.graphql(
        queries.RANKINGS,
        {
            "encounterId": encounter,
            "difficulty": difficulty,
            "className": class_name,
            "specName": spec_name,
            "metric": metric,
            "page": 1,
        },
        cache_kind="rankings",
        cache_ttl=settings.rankings_ttl_seconds,
    )
    payload = (
        (data.get("worldData") or {}).get("encounter") or {}
    ).get("characterRankings") or {}
    rankings = payload if isinstance(payload, list) else payload.get("rankings") or []
    if not rankings:
        # Warcraft Logs spells class names without spaces: DeathKnight, DemonHunter.
        # Getting that wrong returns an empty list rather than an error, which looks
        # exactly like a boss nobody has parsed.
        raise SystemExit(
            f"no ranked {spec_name} {class_name} parses on that boss. Check the class "
            'name: Warcraft Logs writes "DeathKnight" and "DemonHunter" without a space.'
        )

    found: dict[str, tuple[int, str, str]] = {}
    for entry in rankings[:top]:
        report = entry.get("report") or {}
        code, fight_id = report.get("code"), report.get("fightID")
        who = entry.get("name", "")
        if not code or fight_id is None:
            continue
        expression = 'source.name = "{}"'.format(who.replace('"', '\\"'))
        # Casts second so they overwrite buffs: a cast is the button press, which is
        # what a timeline should draw.
        for kind in ("Buffs", "Casts"):
            try:
                result = await client.graphql(
                    EVENTS,
                    {
                        "code": code,
                        "fightId": int(fight_id),
                        "filter": expression,
                        "type": kind,
                    },
                    cache_kind="catalog",
                    cache_ttl=settings.events_ttl_seconds,
                )
            except client.WclError as exc:
                print(f"  (skipped {who}: {exc})")
                continue
            rep = (result.get("reportData") or {}).get("report") or {}
            abilities = (rep.get("masterData") or {}).get("abilities") or []
            meta = {
                a["gameID"]: (a.get("name", ""), a.get("icon", ""))
                for a in abilities
                if a.get("gameID")
            }
            for event in ((rep.get("events") or {}).get("data")) or []:
                ability_id = event.get("abilityGameID")
                if ability_id is None or ability_id not in meta:
                    continue
                name, icon = meta[ability_id]
                if not name:
                    continue
                found[normalise(name)] = (ability_id, name, icon)
    return found


def short(name: str) -> str:
    words = [w for w in name.replace("-", " ").split() if w[:1].isalnum()]
    if len(words) >= 2:
        return "".join(w[0] for w in words[:3]).upper()
    return (name[:3] or "?").title()


async def main_async(args) -> None:
    names = list(args.names or [])
    if args.names_file:
        names += [
            line.strip()
            for line in Path(args.names_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
    if not names:
        raise SystemExit("give --names or --names-file")

    print(
        f"reading the top {args.top} {args.spec} {args.klass} parses on encounter "
        f"{args.encounter} (difficulty {args.difficulty})\n"
    )
    found = await collect(
        args.encounter, args.difficulty, args.klass, args.spec, args.metric, args.top
    )
    print(f"{len(found)} distinct abilities seen across those parses\n")

    matched, missing = [], []
    for wanted in names:
        hit = found.get(normalise(wanted))
        (matched if hit else missing).append((wanted, hit))

    print("paste into the spec's groups in app/spells.py:\n")
    for wanted, hit in matched:
        ability_id, name, icon = hit
        slug = icon.rsplit(".", 1)[0]
        note = "" if normalise(wanted) == normalise(name) else f"  # listed as {wanted!r}"
        print(f'            Spell({ability_id}, "{name}", "{short(name)}", "{slug}"),{note}')

    if missing:
        print(f"\n{len(missing)} not found in these parses:")
        for wanted, _ in missing:
            print(f"    {wanted}")
        print(
            "\n  A miss means a typo, an ability renamed this patch, or one nobody in\n"
            "  the top parses took. Check the spelling first; the matcher already\n"
            "  ignores case, spacing and punctuation."
        )
    print(f"\nbudget: {await client.rate_limit()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class", dest="klass", required=True, help='e.g. "Death Knight"')
    parser.add_argument("--spec", required=True, help="e.g. Frost")
    parser.add_argument("--encounter", type=int, required=True)
    parser.add_argument("--difficulty", type=int, default=4)
    parser.add_argument("--metric", default="dps", help="dps, or hps for healers")
    parser.add_argument("--top", type=int, default=5, help="parses to sample")
    parser.add_argument("--names", nargs="*", help="ability names")
    parser.add_argument("--names-file", help="one ability name per line")
    args = parser.parse_args()

    if not settings.live_enabled:
        raise SystemExit("no Warcraft Logs credentials configured")

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
