"""What the boss and its adds do, as one timeline per encounter and difficulty.

Every spec fighting Ula'tek Heroic sees the same boss, so this is built once per
encounter and difficulty rather than once per board: eighteen timelines for a tier
instead of one for each of the hundreds of boards. That is also why it ships as its
own file rather than being copied into every board.

The times are a median across several top kills, not one pull. Noise does not line
up between pulls and real mechanics do, so taking the median of the nth cast of an
ability across pulls keeps the pattern and drops the accidents.

Which means the row is representative rather than exact, and it cannot be otherwise:
each player row on the board is a different pull with its own timings. The UI says so
next to the row. It also drifts in the later half of a phased fight, where pulls
reach each phase at different times and the median smears across them.
"""

import asyncio
import logging
import statistics
from collections import defaultdict

from ..config import settings
from ..wcl import client, queries
from .catalog import DIFFICULTY_BY_ID

log = logging.getLogger(__name__)

# How many pulls to median across. More is steadier and costs one query each; the
# gain flattens quickly because top kills resemble one another.
SAMPLE_PULLS = 6

FETCH_CONCURRENCY = 3

# Not a caster. Warcraft Logs attributes falling damage and similar to this.
ENVIRONMENT = "Environment"

# Keep a cast index only when this share of sampled pulls reached it. A mechanic
# every pull sees is real; one that shows up once is either a wipe artefact or a
# pull that ran unusually long.
MIN_SHARE = 0.5


async def build(encounter_id: int, difficulty: int, references: list[dict]) -> dict:
    """Aggregate the boss timeline from a list of {code, fightID} references."""
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
    pulls = await asyncio.gather(
        *(_pull(ref, semaphore) for ref in references[:SAMPLE_PULLS]),
        return_exceptions=True,
    )

    good = [p for p in pulls if not isinstance(p, Exception) and p]
    for pull, result in zip(references, pulls):
        if isinstance(result, Exception):
            log.info("boss timeline: skipping %s: %s", pull.get("code"), result)

    if not good:
        return _empty(encounter_id, difficulty)

    boss_name = next((p["boss"] for p in good if p["boss"]), "")

    # (source name, spell id) -> a list per pull of that ability's cast times
    series: dict[tuple[str, int], list[list[float]]] = defaultdict(list)
    meta: dict[tuple[str, int], dict] = {}
    for pull in good:
        for key, times in pull["casts"].items():
            series[key].append(sorted(times))
            meta.setdefault(key, pull["meta"][key])

    casts: list[dict] = []
    abilities: dict[int, dict] = {}
    for (source, spell_id), per_pull in series.items():
        needed = max(1, int(len(good) * MIN_SHARE))
        # The nth cast, medianed across the pulls that got that far.
        for index in range(max(len(t) for t in per_pull)):
            samples = [t[index] for t in per_pull if len(t) > index]
            if len(samples) < needed:
                break
            casts.append(
                {
                    "spellId": spell_id,
                    "toggle": spell_id,
                    "t": round(statistics.median(samples), 1),
                    "name": meta[(source, spell_id)]["name"],
                    "icon": meta[(source, spell_id)]["icon"],
                }
            )
        if any(c["spellId"] == spell_id for c in casts):
            info = meta[(source, spell_id)]
            abilities.setdefault(
                spell_id,
                {
                    "id": spell_id,
                    "name": info["name"],
                    "short": _short(info["name"]),
                    "icon": info["icon"],
                    "source": source,
                    # The boss's own abilities are on by default; its adds are not,
                    # or the row is unreadable on a fight with many of them.
                    "onByDefault": source == boss_name,
                },
            )

    # One ability is often logged under two IDs, the way Caustic Waves and Submerge
    # are here, and the copies land on the same instant. Drawn as-is they stack into
    # an unreadable smudge, so identical name and time collapses to one marker. Two
    # genuinely separate casts of the same ability never share a timestamp.
    casts.sort(key=lambda c: c["t"])
    deduped: list[dict] = []
    seen: set[tuple[str, float]] = set()
    for cast in casts:
        key = (cast["name"], cast["t"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cast)
    casts = deduped

    return {
        "encounter": {"id": encounter_id, "name": boss_name},
        "difficulty": DIFFICULTY_BY_ID.get(
            difficulty, {"id": difficulty, "name": str(difficulty), "short": "?"}
        ),
        "boss": boss_name,
        "samples": len(good),
        "duration": round(statistics.median([p["duration"] for p in good]), 1),
        "abilities": sorted(
            abilities.values(), key=lambda a: (not a["onByDefault"], a["name"])
        ),
        "casts": casts,
    }


def _empty(encounter_id: int, difficulty: int) -> dict:
    return {
        "encounter": {"id": encounter_id, "name": ""},
        "difficulty": DIFFICULTY_BY_ID.get(
            difficulty, {"id": difficulty, "name": str(difficulty), "short": "?"}
        ),
        "boss": "",
        "samples": 0,
        "duration": 0.0,
        "abilities": [],
        "casts": [],
    }


async def _pull(reference: dict, semaphore: asyncio.Semaphore) -> dict | None:
    code, fight_id = reference.get("code"), reference.get("fightID")
    if not code or fight_id is None:
        return None

    async with semaphore:
        data = await client.graphql(
            queries.ENEMY_CASTS,
            {"code": code, "fightId": int(fight_id)},
            cache_kind="enemy",
            cache_ttl=settings.events_ttl_seconds,
        )

    report = (data.get("reportData") or {}).get("report") or {}
    fights = report.get("fights") or []
    if not fights:
        raise ValueError("fight not found in report")
    fight = fights[0]
    start = float(fight.get("startTime") or 0.0)
    end = float(fight.get("endTime") or start)

    master = report.get("masterData") or {}
    actors = {a["id"]: a for a in (master.get("actors") or []) if a.get("id")}
    names = {a["gameID"]: a.get("name", "") for a in (master.get("abilities") or []) if a.get("gameID")}
    icons = {a["gameID"]: a.get("icon", "") for a in (master.get("abilities") or []) if a.get("gameID")}

    # The boss shares its name with the fight, which is how it is told from its adds.
    boss_name = fight.get("name") or ""

    casts: dict[tuple[str, int], list[float]] = defaultdict(list)
    meta: dict[tuple[str, int], dict] = {}
    for event in ((report.get("events") or {}).get("data")) or []:
        if event.get("type") != "cast":
            continue
        spell_id = event.get("abilityGameID")
        source = actors.get(event.get("sourceID"), {}).get("name", "")
        if spell_id is None or not source or source == ENVIRONMENT:
            continue
        name = names.get(spell_id, "")
        if not name:
            continue
        key = (source, spell_id)
        casts[key].append(round((float(event["timestamp"]) - start) / 1000.0, 1))
        meta.setdefault(key, {"name": name, "icon": icons.get(spell_id, "")})

    return {
        "boss": boss_name,
        "duration": round((end - start) / 1000.0, 1),
        "casts": casts,
        "meta": meta,
    }


def _short(name: str) -> str:
    words = [w for w in name.replace("-", " ").split() if w[:1].isalnum()]
    if len(words) >= 2:
        return "".join(w[0] for w in words[:3]).upper()
    return (name[:3] or "?").title()
