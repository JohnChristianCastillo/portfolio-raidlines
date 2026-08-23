"""What raids, bosses and difficulties exist.

Deliberately fetched from Warcraft Logs rather than hardcoded: a raid tier lands
every few months and a hardcoded boss list is a file to remember to edit. The one
judgement call made here is which zones count as raids, since the API does not say
so directly (see is_raid_zone).
"""

from ..config import settings
from ..wcl import client, queries

# Raid difficulty IDs, stable across tiers. LFR (1) is deliberately omitted: nobody
# copies cooldown usage off an LFR parse.
DIFFICULTIES = [
    {"id": 3, "name": "Normal", "short": "N"},
    {"id": 4, "name": "Heroic", "short": "H"},
    {"id": 5, "name": "Mythic", "short": "M"},
]

DIFFICULTY_BY_ID = {d["id"]: d for d in DIFFICULTIES}


def is_raid_zone(zone: dict) -> bool:
    """Raid or dungeon? The API exposes no type flag, so go by difficulties.

    Raid zones offer exactly Normal / Heroic / Mythic (plus LFR). Dungeon zones offer
    Mythic+ and challenge brackets instead, which never match both names exactly.
    """
    names = {d.get("name") for d in zone.get("difficulties") or []}
    return {"Heroic", "Mythic"}.issubset(names) and len(zone.get("encounters") or []) >= 3


async def zones() -> list[dict]:
    """Raid zones, newest expansion and newest tier first.

    Newest first because that is what anyone opening the app wants: the tier being
    progressed right now. Older tiers stay reachable rather than being dropped, since
    the data is just as valid and costs nothing extra to list.
    """
    data = await client.graphql(
        queries.ZONES,
        {},
        cache_kind="zones",
        cache_ttl=settings.catalog_ttl_seconds,
    )

    out: list[dict] = []
    expansions = (data.get("worldData") or {}).get("expansions") or []
    for expansion in expansions:
        for zone in expansion.get("zones") or []:
            if not is_raid_zone(zone):
                continue
            out.append(
                {
                    "id": zone["id"],
                    "name": zone["name"],
                    "expansion": expansion.get("name", ""),
                    "expansionId": expansion.get("id", 0),
                    # frozen means the tier is over and its rankings will not change.
                    "frozen": bool(zone.get("frozen")),
                    "encounters": [
                        {"id": e["id"], "name": e["name"]}
                        for e in zone.get("encounters") or []
                    ],
                }
            )

    # Sort explicitly rather than trusting the order the API happens to return.
    # Reversing that order was wrong: it put a Mists of Pandaria tier at the top.
    # Both IDs are assigned in release order, so descending is newest first, and it
    # stays correct whichever way the API decides to hand the arrays over.
    #
    # Active tiers outrank frozen ones within an expansion, and that is not a nicety.
    # Warcraft Logs can carry two zones for the same raid, one still open and one
    # frozen with its own encounter IDs. Highest ID alone picked the frozen twin, so
    # the app would have opened on a closed tier by default.
    out.sort(key=lambda z: (z["expansionId"], not z["frozen"], z["id"]), reverse=True)
    return out
