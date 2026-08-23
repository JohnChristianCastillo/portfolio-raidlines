"""Check the configured hero talent trees against live parses.

    python tools/herotrees.py --encounter 3470 --difficulty 4

Reports how the sampled parses split between the trees in HERO_TREES, and flags any
parse it cannot classify. An unclassified parse means the entry IDs have gone stale,
which is what happens when a patch rebuilds a talent tree.

Note on what this tool does NOT do. It cannot find the trees for you. An earlier
version tried, by looking for the most evenly split pair of mutually exclusive
talent nodes, on the theory that a hero tree is a real choice while ordinary talents
are near-unanimous. That is wrong twice over: plenty of ordinary either/or nodes
split evenly, and a hero tree can be unanimous. Every one of 232 sampled Subtlety
parses runs Deathstalker, so the true hero node looked like no choice at all while
an ordinary talent node split 68/32 and looked exactly like one.

The trees have to be read off the game's talent pane instead. The middle of the
three trees is the hero tree; take the entry ID of each of its two root nodes and
put them in HERO_TREES. Entry ID, not node ID and not spell ID: a ranking's talents
list carries entry IDs.

Costs nothing beyond the rankings query: talents come free with includeCombatantInfo.
"""

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.config import settings  # noqa: E402
from app.spells import HERO_TREES, SPEC_QUERY_NAMES  # noqa: E402
from app.wcl import client, queries  # noqa: E402


async def sample(encounter: int, difficulty: int, spec_key: str) -> list[tuple]:
    class_name, spec_name = SPEC_QUERY_NAMES[spec_key]
    data = await client.graphql(
        queries.RANKINGS,
        {
            "encounterId": encounter,
            "difficulty": difficulty,
            "className": class_name,
            "specName": spec_name,
            "page": 1,
        },
        cache_kind="rankings",
        cache_ttl=settings.rankings_ttl_seconds,
    )
    payload = (
        (data.get("worldData") or {}).get("encounter") or {}
    ).get("characterRankings") or {}
    rankings = payload if isinstance(payload, list) else payload.get("rankings") or []

    out = []
    for entry in rankings:
        talents = {t["talentID"] for t in (entry.get("talents") or [])}
        if talents:
            out.append((entry.get("name", "?"), entry.get("report") or {}, talents))
    return out


async def main_async(args) -> None:
    trees = HERO_TREES.get(args.spec, [])
    if not trees:
        raise SystemExit(f"no hero trees configured for {args.spec} in app/spells.py")

    rows = await sample(args.encounter, args.difficulty, args.spec)
    if not rows:
        raise SystemExit("no parses with talent data")

    counts: Counter = Counter()
    unclassified = []
    multiple = []
    for name, report, talents in rows:
        hits = [t for t in trees if t.entry_id in talents]
        if not hits:
            unclassified.append((name, report))
        elif len(hits) > 1:
            multiple.append((name, [t.name for t in hits]))
        else:
            counts[hits[0].name or f"entry {hits[0].entry_id}"] += 1

    n = len(rows)
    print(f"{n} parses sampled\n")
    for tree in trees:
        label = tree.name or f"(unnamed) entry {tree.entry_id}"
        c = counts.get(tree.name or f"entry {tree.entry_id}", 0)
        print(f"  {label:<22} {c:>4}  ({c * 100 // n if n else 0}%)  entry {tree.entry_id}")

    if multiple:
        print(f"\n{len(multiple)} parses matched MORE THAN ONE tree, which should be")
        print("impossible. The entry IDs are probably wrong:")
        for name, hits in multiple[:5]:
            print(f"   {name}: {hits}")

    if unclassified:
        print(f"\n{len(unclassified)} parses matched NO tree. Either a tree is missing")
        print("from HERO_TREES, or a patch has changed the entry IDs:")
        for name, report in unclassified[:5]:
            code, fight = report.get("code"), report.get("fightID")
            print(f"   {name}: https://www.warcraftlogs.com/reports/{code}?fight={fight}")
    elif not multiple:
        print("\nEvery parse classified. The configured entry IDs are current.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encounter", type=int, required=True, help="boss ID")
    parser.add_argument("--difficulty", type=int, default=4, help="3 N, 4 H, 5 M")
    parser.add_argument("--spec", default="rogue-subtlety")
    args = parser.parse_args()

    if not settings.live_enabled:
        raise SystemExit("no Warcraft Logs credentials configured")

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
