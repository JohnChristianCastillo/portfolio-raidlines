"""List every ability a player actually cast in a logged fight.

    python tools/discover.py --code aBcDeFgH --fight 12
    python tools/discover.py --encounter 3470 --difficulty 5   # top parse, auto

This exists to curate the potions and trinkets groups in app/spells.py without
guessing. Those two groups are season-specific, and a spell ID typed in from memory
that is subtly wrong does not error: it silently matches nothing and the toggle draws
an empty row forever. Reading the IDs off a real log removes the guess.

Output is grouped so the interesting rows stand out, and the last column is a line
ready to paste into the catalog.

Costs a few points: unlike the app's own queries this one deliberately does NOT
filter by ability, since the whole point is to see what is there.
"""

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Player and ability names are routinely Korean, Chinese or accented, and the Windows
# console defaults to cp1252, which cannot encode them. Without this the tool dies on
# a UnicodeEncodeError while printing a name, which is a silly way to lose a query
# that has already been paid for out of the point budget.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.config import settings  # noqa: E402
from app.spells import spec_for, spell_index  # noqa: E402
from app.wcl import client, queries  # noqa: E402

# Casts with no filter expression at all. Everything else in the app filters
# server-side; here we want the whole list precisely because we do not know it yet.
ALL_CASTS = """
query AllCasts($code: String!, $fightId: Int!, $filter: String!) {
  reportData {
    report(code: $code) {
      masterData { abilities { gameID name icon } }
      fights(fightIDs: [$fightId]) { id name startTime endTime }
      events(
        fightIDs: [$fightId]
        dataType: Casts
        filterExpression: $filter
        limit: 5000
      ) { data }
    }
  }
}
"""

# Rough buckets, by what the ability's name looks like. Only a hint for the eye: the
# IDs are what matter and they are all printed regardless.
POTION_WORDS = ("potion", "flask", "elixir", "healthstone", "phial")


async def top_parse(encounter: int, difficulty: int, spec_key: str) -> tuple[str, int, str]:
    """The rank 1 parse's report, fight and player, so --encounter alone is enough."""
    spec = spec_for(spec_key)
    if spec is None:
        raise SystemExit(f"unknown spec {spec_key!r}")
    data = await client.graphql(
        queries.RANKINGS,
        {
            "encounterId": encounter,
            "difficulty": difficulty,
            "className": spec.class_name,
            "specName": spec.spec_name,
            "metric": spec.metric,
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
        raise SystemExit("no ranked parses for that boss and difficulty")
    best = rankings[0]
    report = best.get("report") or {}
    return report["code"], int(report["fightID"]), best.get("name", "")


async def run(code: str, fight_id: int, source: str, spec_key: str) -> None:
    expression = f'source.name = "{source}"' if source else "source.type = \"Player\""

    data = await client.graphql(
        ALL_CASTS,
        {"code": code, "fightId": fight_id, "filter": expression},
        cache_kind="discover",
        cache_ttl=settings.events_ttl_seconds,
    )

    report = (data.get("reportData") or {}).get("report") or {}
    abilities = (report.get("masterData") or {}).get("abilities") or []
    names = {a["gameID"]: a.get("name", "") for a in abilities if a.get("gameID")}
    icons = {a["gameID"]: a.get("icon", "") for a in abilities if a.get("gameID")}

    events = ((report.get("events") or {}).get("data")) or []
    counts = Counter(
        e.get("abilityGameID")
        for e in events
        if e.get("type") == "cast" and e.get("abilityGameID") is not None
    )
    if not counts:
        raise SystemExit("no casts found (private report, or wrong player name?)")

    known = spell_index(spec_key)

    print(f"\n{source or 'all players'} in report {code} fight {fight_id}")
    print(f"{len(counts)} distinct abilities cast\n")
    print(f"{'casts':>5}  {'id':>9}  {'name':<32} catalog line")
    print("-" * 100)

    for ability_id, count in counts.most_common():
        name = names.get(ability_id, "?")
        icon = icons.get(ability_id, "")
        if ability_id in known:
            marker = "already tracked"
        elif any(word in name.lower() for word in POTION_WORDS):
            # The reason most people run this: potions are the hard ones to name.
            marker = f'Spell({ability_id}, "{name}", "{_short(name)}", "{icon}"),'
        else:
            marker = f'Spell({ability_id}, "{name}", "{_short(name)}", "{icon}"),'
        print(f"{count:>5}  {ability_id:>9}  {name[:32]:<32} {marker}")

    print(
        "\nCopy the lines you want into the right group in app/spells.py. "
        "Filler and builder spells are in this list too; the point is to pick from it."
    )


def _short(name: str) -> str:
    """A 2-3 character badge, the fallback when an icon will not load."""
    words = [w for w in name.replace("-", " ").split() if w[:1].isalnum()]
    if len(words) >= 2:
        return "".join(w[0] for w in words[:3]).upper()
    return name[:3].title()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", help="report code, from its warcraftlogs.com URL")
    parser.add_argument("--fight", type=int, help="fight ID within that report")
    parser.add_argument("--player", default="", help="source name; omit for everyone")
    parser.add_argument("--encounter", type=int, help="boss ID, to use its top parse")
    parser.add_argument("--difficulty", type=int, default=5)
    parser.add_argument("--spec", default="rogue-subtlety")
    args = parser.parse_args()

    if not settings.live_enabled:
        raise SystemExit(
            "no Warcraft Logs credentials configured (or RAIDLINE_FORCE_FIXTURES is "
            "set). See _local/wcl_api_registration/how_to_setup.md"
        )

    async def go() -> None:
        code, fight_id, player = args.code, args.fight, args.player
        if not code or fight_id is None:
            if args.encounter is None:
                raise SystemExit("give either --code with --fight, or --encounter")
            code, fight_id, player = await top_parse(
                args.encounter, args.difficulty, args.spec
            )
            print(f"using the rank 1 parse: {player}, report {code} fight {fight_id}")
        await run(code, fight_id, player, args.spec)
        print(f"\nbudget: {await client.rate_limit()}")

    asyncio.run(go())


if __name__ == "__main__":
    main()
