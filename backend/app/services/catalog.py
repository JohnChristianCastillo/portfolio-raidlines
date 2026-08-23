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

    The encounter-count floor also drops the "Complete Raid" meta-zones, which bundle
    a whole tier behind one synthetic encounter, and unreleased tiers listed with no
    encounters at all.
    """
    names = {d.get("name") for d in zone.get("difficulties") or []}
    return {"Heroic", "Mythic"}.issubset(names) and len(zone.get("encounters") or []) >= 3


def is_test_realm(zone: dict, live_names: set[str]) -> bool:
    """Is this a PTR or beta copy rather than the raid people actually play?

    Warcraft Logs keeps test-realm zones alongside live ones. They matter here
    because they pass every other check: same name, same difficulties, a full boss
    list, and encounter IDs that differ only by a digit glued on the front (live 3470
    becomes 53470). Picking one up means showing rankings from a closed beta realm.

    Two signals, because the naming is inconsistent:
      - an explicit "(PTR)" or "(Beta)" in the name, which is how most are marked
      - a frozen zone whose name matches a zone that is still live, which is how the
        unlabelled ones show up. The Venomous Abyss has exactly this shape: zone 53
        open with 9 bosses, zone 54 frozen with the same name and 8.
    """
    name = zone.get("name", "")
    if "(PTR)" in name or "(Beta)" in name:
        return True
    return bool(zone.get("frozen")) and name in live_names


async def zones() -> list[dict]:
    """The raids worth showing, newest first.

    Scoped to the current expansion by default. Warcraft Logs happily lists every
    tier back to Classic, but this is built to be shown to people raiding now, and a
    dropdown of twenty-six mostly dead tiers buries the one they came for. Set
    RAIDLINES_CURRENT_EXPANSION_ONLY=0 to get the lot back; nothing else changes.
    """
    data = await client.graphql(
        queries.ZONES,
        {},
        cache_kind="zones",
        cache_ttl=settings.catalog_ttl_seconds,
    )

    expansions = (data.get("worldData") or {}).get("expansions") or []
    if not expansions:
        return []

    if settings.current_expansion_only:
        # Highest expansion ID is the current one. Sorting rather than taking the
        # first or last element, because the API's array order is not something to
        # rely on: trusting it is what put a Mists of Pandaria tier at the top before.
        expansions = [max(expansions, key=lambda e: e.get("id", 0))]

    out: list[dict] = []
    for expansion in expansions:
        raids = [z for z in expansion.get("zones") or [] if is_raid_zone(z)]
        # Collected before filtering, so a frozen zone can be recognised as the test
        # copy of a raid that is still open.
        live_names = {z["name"] for z in raids if not z.get("frozen")}

        for zone in raids:
            if is_test_realm(zone, live_names):
                continue
            out.append(
                {
                    "id": zone["id"],
                    "name": zone["name"],
                    "expansion": expansion.get("name", ""),
                    "expansionId": expansion.get("id", 0),
                    # frozen means Warcraft Logs has closed the zone: no new rankings
                    # will ever be added to it. For a real tier that means the tier is
                    # over.
                    "frozen": bool(zone.get("frozen")),
                    "encounters": [
                        {"id": e["id"], "name": e["name"]}
                        for e in zone.get("encounters") or []
                    ],
                }
            )

    # Newest first. Zone IDs are handed out in release order, so descending puts the
    # tier being progressed right now at the top and the dropdown reads backwards in
    # time from there.
    out.sort(key=lambda z: (z["expansionId"], z["id"]), reverse=True)
    return out
