"""Turning ranked parses into comparable timelines.

The shape of the work, per boss + difficulty + spec:

  1. Ask Warcraft Logs for the top N character rankings by DPS. Each ranking points
     at the report and fight it came from.
  2. For each of those, pull that one player's casts of the tracked spells within
     that one fight.
  3. Rebase every cast to seconds since the pull, so ten different logs of different
     lengths can be laid over one another and read as one picture.

Two decisions worth knowing about:

Every tracked spell is fetched, not just the ones currently toggled on. Toggling is
then a filter over data already in the browser rather than a fresh round trip, which
keeps the UI instant and keeps us inside the hourly point budget. The set of spells
fetched is exactly the catalog in spells.py.

The per-player fetches run concurrently but capped. Ten parallel event queries would
be fine for our laptop and rude to Warcraft Logs; the semaphore keeps a few in flight
without turning one boss click into a burst.
"""

import asyncio
import logging

from ..config import settings
from ..spells import SPEC_LABELS, SPEC_QUERY_NAMES, spell_ids_for, spell_index
from ..wcl import client, queries
from .catalog import DIFFICULTY_BY_ID

log = logging.getLogger(__name__)

# How many player-fight queries may be in flight at once.
FETCH_CONCURRENCY = 4


class UnknownSpec(ValueError):
    """Asked for a spec that is not in the catalog."""


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

    tracked = spell_ids_for(spec_key)
    if not tracked:
        warnings.append(
            "No spells are configured for this spec, so every timeline is empty. "
            "Add them in backend/app/spells.py."
        )

    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
    players = await asyncio.gather(
        *(
            _player(rank, entry, spec_key, tracked, semaphore)
            for rank, entry in enumerate(rankings, start=1)
        ),
        return_exceptions=True,
    )

    kept: list[dict] = []
    for entry, result in zip(rankings, players):
        if isinstance(result, Exception):
            # One unreadable log should cost that row, not the whole page. Private and
            # deleted reports are the usual cause and they are entirely normal.
            name = entry.get("name", "?")
            log.warning("dropping %s: %s", name, result)
            warnings.append(f"Could not read {name}'s log: {result}")
            continue
        kept.append(result)

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
        "warnings": warnings,
    }


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


async def _player(
    rank: int,
    entry: dict,
    spec_key: str,
    tracked: list[int],
    semaphore: asyncio.Semaphore,
) -> dict:
    report = entry.get("report") or {}
    code = report.get("code")
    fight_id = report.get("fightID")
    name = entry.get("name") or "Unknown"
    if not code or fight_id is None:
        raise ValueError("ranking carries no report reference")

    async with semaphore:
        fight = await _fight(code, int(fight_id), name, tracked)

    server = entry.get("server") or {}
    guild = entry.get("guild") or {}

    return {
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
        "reportUrl": f"https://www.warcraftlogs.com/reports/{code}#fight={fight_id}",
        "casts": fight["casts"],
    }


async def _fight(code: str, fight_id: int, source_name: str, tracked: list[int]) -> dict:
    """One player's tracked casts in one logged pull, rebased to seconds since pull."""
    variables = {
        "code": code,
        "fightId": fight_id,
        # Filtering server-side is the difference between a few hundred bytes and the
        # entire cast log of a seven minute fight, and the rate limit charges by data
        # returned. An empty tracked list would match everything, so guard it.
        "filter": _filter_expression(source_name, tracked),
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

    icons = {
        a.get("gameID"): a.get("icon", "")
        for a in ((report.get("masterData") or {}).get("abilities") or [])
        if a.get("gameID") is not None
    }
    names = {
        a.get("gameID"): a.get("name", "")
        for a in ((report.get("masterData") or {}).get("abilities") or [])
        if a.get("gameID") is not None
    }

    events = ((report.get("events") or {}).get("data")) or []
    casts = []
    for event in events:
        # dataType Casts returns begincast as well as cast. Counting both would draw
        # every channelled or cast-time ability twice.
        if event.get("type") != "cast":
            continue
        ability_id = event.get("abilityGameID")
        if ability_id not in tracked:
            continue
        casts.append(
            {
                "spellId": ability_id,
                "t": round((float(event["timestamp"]) - start) / 1000.0, 1),
                "name": names.get(ability_id, ""),
                "icon": icons.get(ability_id, ""),
            }
        )
    casts.sort(key=lambda c: c["t"])

    return {
        "duration": round((end - start) / 1000.0, 1),
        "kill": bool(fight.get("kill")),
        "casts": casts,
    }


def _filter_expression(source_name: str, tracked: list[int]) -> str:
    if not tracked:
        # Matches nothing, cheaply. Better than omitting the filter, which would match
        # every cast in the fight.
        return 'ability.id = 0 and source.name = ""'
    ids = ", ".join(str(i) for i in tracked)
    escaped = source_name.replace('"', '\\"')
    return f'source.name = "{escaped}" and ability.id in ({ids})'


def spell_names(spec_key: str) -> dict[int, str]:
    """Catalog display names, used when a report's masterData is unavailable."""
    return {sid: spell.name for sid, spell in spell_index(spec_key).items()}
