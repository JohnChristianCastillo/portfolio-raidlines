"""Turning ranked parses into comparable timelines.

Per boss + difficulty + spec:

  1. Ask Warcraft Logs for the top N character rankings by DPS. Each ranking points
     at the report and fight it came from, and carries the player's gear.
  2. Pull that player's casts from that fight.
  3. Rebase every cast to seconds since the pull, so ten logs of different lengths
     can be laid over one another and read as one picture.

Casts are fetched unfiltered and selected here. An ability-filtered query costs the
same 2 points as an unfiltered one, so filtering server-side only lost information:
trinkets are found from what players actually cast, and editing the catalog does not
invalidate a single cached fight.

The trinket group is built per board rather than hand-maintained. Gear slots 12 and
13 of each ranking are the equipped trinkets; a cast whose icon or name matches one
of them is a trinket use. That keeps the toggles to what these ten players brought
to this boss, which is the only trinket list worth showing.
"""

import asyncio
import logging

from ..config import settings
from ..spells import SPEC_LABELS, SPEC_QUERY_NAMES, groups_for, spell_index
from ..wcl import client, queries
from .catalog import DIFFICULTY_BY_ID

log = logging.getLogger(__name__)

# How many player-fight queries may be in flight at once.
FETCH_CONCURRENCY = 4

# Gear array positions of the two trinkets. Fixed by the game's slot order.
TRINKET_SLOTS = (12, 13)

# The catalog group that discovered trinkets are attached to.
TRINKET_GROUP = "trinkets"


class UnknownSpec(ValueError):
    """Asked for a spec that is not in the catalog."""


def _norm_icon(icon: str) -> str:
    """Icons arrive with and without their extension depending on the field."""
    return (icon or "").rsplit(".", 1)[0].lower()


async def build(encounter_id: int, difficulty: int, spec_key: str) -> dict:
    """The one call the API layer makes. Returns a fully rendered timeline payload."""
    if spec_key not in SPEC_QUERY_NAMES:
        raise UnknownSpec(f"unknown spec {spec_key!r}")

    class_name, spec_name = SPEC_QUERY_NAMES[spec_key]
    warnings: list[str] = []

    rankings, encounter_name = await _rankings(
        encounter_id, difficulty, class_name, spec_name
    )
    rankings = rankings[: settings.top_n]

    if not rankings:
        warnings.append(
            f"Warcraft Logs has no ranked {spec_name} {class_name} parses for this "
            "boss and difficulty yet."
        )

    catalog = spell_index(spec_key)

    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
    results = await asyncio.gather(
        *(
            _player(rank, entry, catalog, semaphore)
            for rank, entry in enumerate(rankings, start=1)
        ),
        return_exceptions=True,
    )

    kept: list[dict] = []
    trinkets: dict[int, dict] = {}
    for entry, result in zip(rankings, results):
        if isinstance(result, Exception):
            # One unreadable log should cost that row, not the whole page. Private and
            # deleted reports are the usual cause and they are entirely normal.
            name = entry.get("name", "?")
            log.warning("dropping %s: %s", name, result)
            warnings.append(f"Could not read {name}'s log: {result}")
            continue
        player, found = result
        kept.append(player)
        for spell_id, spell in found.items():
            trinkets.setdefault(spell_id, spell)

    # The ruler has to span the longest pull, otherwise the slowest kill runs off it.
    max_duration = max((p["duration"] for p in kept), default=0.0)

    return {
        "encounter": {"id": encounter_id, "name": encounter_name},
        "difficulty": DIFFICULTY_BY_ID.get(
            difficulty, {"id": difficulty, "name": str(difficulty), "short": "?"}
        ),
        "spec": {"key": spec_key, "label": SPEC_LABELS.get(spec_key, spec_key)},
        "maxDuration": max_duration,
        "players": kept,
        # The catalog groups, with the trinket group filled in from this board.
        "groups": _groups(spec_key, trinkets),
        "warnings": warnings,
    }


def _groups(spec_key: str, trinkets: dict[int, dict]) -> list[dict]:
    out = []
    for group in groups_for(spec_key):
        spells = [
            {
                "id": s.id,
                "name": s.name,
                "short": s.short,
                "icon": s.icon,
                "onByDefault": s.on_by_default,
            }
            for s in group.spells
        ]
        if group.key == TRINKET_GROUP:
            spells.extend(
                sorted(trinkets.values(), key=lambda s: s["name"] or str(s["id"]))
            )
        out.append(
            {
                "key": group.key,
                "label": group.label,
                "color": group.color,
                "spells": spells,
            }
        )
    return out


async def _rankings(
    encounter_id: int, difficulty: int, class_name: str, spec_name: str
) -> tuple[list[dict], str]:
    variables = {
        "encounterId": encounter_id,
        "difficulty": difficulty,
        "className": class_name,
        "specName": spec_name,
        "page": 1,
    }
    data = await client.graphql(
        queries.RANKINGS,
        variables,
        cache_kind="rankings",
        cache_ttl=settings.rankings_ttl_seconds,
    )
    encounter = (data.get("worldData") or {}).get("encounter") or {}
    # characterRankings is an untyped JSON scalar, so nothing about its shape is
    # guaranteed by the schema. Read it defensively.
    payload = encounter.get("characterRankings") or {}
    if isinstance(payload, list):  # older shape, seen on some endpoints
        rankings = payload
    else:
        rankings = payload.get("rankings") or []
    return rankings, encounter.get("name", "")


def _equipped_trinkets(entry: dict) -> list[dict]:
    gear = entry.get("gear") or []
    out = []
    for slot in TRINKET_SLOTS:
        if slot < len(gear):
            item = gear[slot] or {}
            if item.get("id"):
                out.append(
                    {
                        "id": item["id"],
                        "name": item.get("name", ""),
                        "icon": item.get("icon", ""),
                    }
                )
    return out


async def _player(
    rank: int,
    entry: dict,
    catalog: dict,
    semaphore: asyncio.Semaphore,
) -> tuple[dict, dict[int, dict]]:
    report = entry.get("report") or {}
    code = report.get("code")
    fight_id = report.get("fightID")
    name = entry.get("name") or "Unknown"
    if not code or fight_id is None:
        raise ValueError("ranking carries no report reference")

    equipped = _equipped_trinkets(entry)

    async with semaphore:
        fight = await _fight(code, int(fight_id), name, catalog, equipped)

    server = entry.get("server") or {}
    guild = entry.get("guild") or {}

    player = {
        "rank": rank,
        "name": name,
        "server": server.get("name", ""),
        "region": (server.get("region") or "").upper(),
        "guild": guild.get("name", ""),
        # Warcraft Logs reports the ranking metric as a rate already, and durations
        # in milliseconds.
        "amount": float(entry.get("amount") or 0.0),
        "duration": fight["duration"],
        "kill": fight["kill"],
        "reportCode": code,
        "fightId": int(fight_id),
        # Report-scoped player ID, needed to ask for the talent loadout. Taken from
        # the cast events, so it costs no extra query. None if they cast nothing.
        "actorId": fight["actor_id"],
        "trinkets": equipped,
        "reportUrl": f"https://www.warcraftlogs.com/reports/{code}#fight={fight_id}",
        "casts": fight["casts"],
    }
    return player, fight["trinket_spells"]


async def _fight(
    code: str,
    fight_id: int,
    source_name: str,
    catalog: dict,
    equipped: list[dict],
) -> dict:
    """One player's casts in one logged pull, rebased to seconds since the pull."""
    variables = {
        "code": code,
        "fightId": fight_id,
        "filter": _filter_expression(source_name),
    }
    data = await client.graphql(
        queries.FIGHT,
        variables,
        cache_kind="fight",
        # A logged fight is immutable, so this can be cached for as long as we like.
        cache_ttl=settings.events_ttl_seconds,
    )

    report = (data.get("reportData") or {}).get("report") or {}
    fights = report.get("fights") or []
    if not fights:
        raise ValueError("fight not found in report (deleted or private)")
    fight = fights[0]

    start = float(fight.get("startTime") or 0.0)
    end = float(fight.get("endTime") or start)

    abilities = (report.get("masterData") or {}).get("abilities") or []
    icons = {a["gameID"]: a.get("icon", "") for a in abilities if a.get("gameID")}
    names = {a["gameID"]: a.get("name", "") for a in abilities if a.get("gameID")}

    trinket_icons = {_norm_icon(t["icon"]) for t in equipped if t.get("icon")}
    trinket_names = {t["name"].lower() for t in equipped if t.get("name")}

    events = ((report.get("events") or {}).get("data")) or []
    casts: list[dict] = []
    found: dict[int, dict] = {}
    actor_id = None

    for event in events:
        # dataType Casts returns begincast as well as cast. Counting both would draw
        # every channelled or cast-time ability twice.
        if event.get("type") != "cast":
            continue
        ability_id = event.get("abilityGameID")
        if ability_id is None:
            continue
        if actor_id is None:
            actor_id = event.get("sourceID")

        icon = icons.get(ability_id, "")
        ability_name = names.get(ability_id, "")

        known = ability_id in catalog
        is_trinket = _norm_icon(icon) in trinket_icons or (
            ability_name and ability_name.lower() in trinket_names
        )
        if not known and not is_trinket:
            # Builders, spenders and everything else the fight is full of.
            continue

        if is_trinket and not known:
            found.setdefault(
                ability_id,
                {
                    "id": ability_id,
                    "name": ability_name or f"Trinket {ability_id}",
                    "short": _short(ability_name),
                    "icon": icon,
                    "onByDefault": False,
                },
            )

        casts.append(
            {
                "spellId": ability_id,
                "t": round((float(event["timestamp"]) - start) / 1000.0, 1),
                "name": ability_name,
                "icon": icon,
            }
        )

    casts.sort(key=lambda c: c["t"])

    return {
        "duration": round((end - start) / 1000.0, 1),
        "kill": bool(fight.get("kill")),
        "casts": casts,
        "actor_id": actor_id,
        "trinket_spells": found,
    }


def _short(name: str) -> str:
    """A 2-3 character badge, the fallback when an icon will not load."""
    words = [w for w in name.replace("-", " ").split() if w[:1].isalnum()]
    if len(words) >= 2:
        return "".join(w[0] for w in words[:3]).upper()
    return (name[:3] or "?").title()


def _filter_expression(source_name: str) -> str:
    escaped = source_name.replace('"', '\\"')
    return f'source.name = "{escaped}"'


async def talents(code: str, fight_id: int, actor_id: int) -> str:
    """The player's talent loadout as an in-game import string.

    Fetched on demand rather than with the board: it is only ever read when someone
    opens a player's note, and asking for ten of them up front would be ten queries
    nobody looked at.
    """
    data = await client.graphql(
        queries.TALENTS,
        {"code": code, "fightId": fight_id, "actorId": actor_id},
        cache_kind="talents",
        cache_ttl=settings.events_ttl_seconds,
    )
    fights = ((data.get("reportData") or {}).get("report") or {}).get("fights") or []
    if not fights:
        raise ValueError("fight not found in report")
    return fights[0].get("talentImportCode") or ""
