"""Find the talent node that tells one hero tree from another.

    python tools/herotrees.py --encounter 3470 --difficulty 4

Warcraft Logs exposes which talent nodes a player took but not which hero tree those
nodes belong to, and there is no field in the schema for it. What the data does show
is the choice: across a spec's parses, exactly one node from each hero tree is
present, never two and never none.

So this samples the ranked parses, finds the nodes that split the population, and
checks each candidate pair for mutual exclusivity. A pair that is perfectly
exclusive over a decent sample is the hero tree choice. It then prints a log link
for one player from each side, so the trees can be named by looking.

Naming is the one step that cannot be automated. Put the result in HERO_TREES in
app/spells.py; until a name is filled in, no hero icon is drawn.

Costs nothing beyond the rankings query: talents come free with includeCombatantInfo.
"""

import argparse
import asyncio
import sys
from collections import Counter
from itertools import combinations
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


def report_url(report: dict) -> str:
    code, fight = report.get("code"), report.get("fightID")
    return f"https://www.warcraftlogs.com/reports/{code}?fight={fight}"


async def main_async(args) -> None:
    rows = await sample(args.encounter, args.difficulty, args.spec)
    n = len(rows)
    if n < 4:
        raise SystemExit(f"only {n} parses with talent data, too few to judge")

    counts = Counter()
    for _, _, talents in rows:
        counts.update(talents)
    split = [i for i, c in counts.items() if 1 <= c <= n - 1]

    print(f"{n} parses sampled, {len(split)} non-universal talent nodes\n")

    exclusive = []
    for a, b in combinations(split, 2):
        both = neither = 0
        for _, _, talents in rows:
            has_a, has_b = a in talents, b in talents
            if has_a and has_b:
                both += 1
            elif not has_a and not has_b:
                neither += 1
        if both == 0 and neither == 0:
            exclusive.append((a, b, counts[a], counts[b]))

    # Rank by how evenly the pair splits the population. Plenty of ordinary either/or
    # talent nodes are mutually exclusive too, but they come out 98/2 because almost
    # everyone picks the same one. A hero tree is a real choice, so its split is far
    # closer to even, and that is the whole signal.
    exclusive.sort(key=lambda x: abs(x[2] - x[3]))

    if not exclusive:
        print("No mutually exclusive pair found. Either every parse in this sample")
        print("runs the same hero tree, or the sample is too small. Try another")
        print("boss, or heroic difficulty, where builds vary more.")
        return

    known = {t.node_id for trees in HERO_TREES.values() for t in trees}
    print("candidates, most evenly split first (the top one is the likely tree):\n")
    for a, b, ca, cb in exclusive[: args.top]:
        mark = "  (already in HERO_TREES)" if a in known and b in known else ""
        print(f"candidate pair: {a} ({ca}/{n}) vs {b} ({cb}/{n}){mark}")
        for node in (a, b):
            who = next(r for r in rows if node in r[2])
            print(f"   node {node}: {who[0]} -> {report_url(who[1])}")
        print()

    print("Open one player from each side, read which hero tree they run, and put")
    print("the names into HERO_TREES in app/spells.py.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encounter", type=int, required=True, help="boss ID")
    parser.add_argument("--difficulty", type=int, default=4, help="3 N, 4 H, 5 M")
    parser.add_argument("--spec", default="rogue-subtlety")
    parser.add_argument("--top", type=int, default=3, help="candidate pairs to show")
    args = parser.parse_args()

    if not settings.live_enabled:
        raise SystemExit("no Warcraft Logs credentials configured")

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
