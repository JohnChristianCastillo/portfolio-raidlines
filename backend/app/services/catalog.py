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
    for expansion in reversed(expansions):
        for zone in reversed(expansion.get("zones") or []):
            if not is_raid_zone(zone):
                continue
            out.append(
                {
                    "id": zone["id"],
                    "name": zone["name"],
                    "expansion": expansion.get("name", ""),
                    # frozen means the tier is over and its rankings will not change.
                    "frozen": bool(zone.get("frozen")),
                    "encounters": [
                        {"id": e["id"], "name": e["name"]}
                        for e in zone.get("encounters") or []
                    ],
                }
            )
    return out
