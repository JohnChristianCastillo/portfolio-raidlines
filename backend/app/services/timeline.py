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

Trinkets and potions are both discovered per board rather than hand-maintained, so
neither needs touching when a season turns over. Trinkets come from gear slots 12
and 13 of each ranking, matched against casts by icon or name. Potions are matched
on the alchemy and potion icon families plus the obvious names.

Order matters in that classification: Freightrunner's Flask is a trinket whose icon
is an alchemy flask, so the gear match has to be tried before the potion heuristic
or it lands in the wrong group.

Trinkets are labelled and toggled by the ITEM, never by the ability. One trinket can
fire under several names (Light Company Guidon casts "Charge!"), so keying off the
ability both mislabels the toggle and splits one trinket across several of them.
Hence the `toggle` on every cast: the trinket item for a trinket, the spell itself
for everything else. The MRT export still writes the real spell ID.
"""

import asyncio
import logging

from ..config import settings
from ..spells import groups_for, hero_slug, hero_tree_for, spec_for, spell_index
from ..wcl import client, queries
from . import herotalents
from .catalog import DIFFICULTY_BY_ID

log = logging.getLogger(__name__)

# How many player-fight queries may be in flight at once.
FETCH_CONCURRENCY = 4

# What Warcraft Logs calls a player who has opted out of rankings.
ANONYMOUS = "Anonymous"

# Gear array positions of the two trinkets. Fixed by the game's slot order.
TRINKET_SLOTS = (12, 13)

# Catalog groups filled in from the logs rather than from spells.py.
TRINKET_GROUP = "trinkets"
POTION_GROUP = "potions"

# What a consumable looks like. Both lists were read off the icons and names that
# actually appear in ranked parses, not guessed.
POTION_ICON_HINTS = ("alchemy", "potion")
POTION_NAME_HINTS = (
    "potion",
    "flask",
    "elixir",
    "phial",
    "healthstone",
    "draught",
)


class UnknownSpec(ValueError):
    """Asked for a spec that is not in the catalog."""


def _norm_icon(icon: str) -> str:
    """Icons arrive with and without their extension depending on the field."""
    return (icon or "").rsplit(".", 1)[0].lower()


async def build(encounter_id: int, difficulty: int, spec_key: str) -> dict:
    """The one call the API layer makes. Returns a fully rendered timeline payload."""
    spec = spec_for(spec_key)
    if spec is None:
        raise UnknownSpec(f"unknown spec {spec_key!r}")

    warnings: list[str] = []

    rankings, encounter_name = await _rankings(encounter_id, difficulty, spec)
    rankings = rankings[: settings.top_n]

    if not rankings:
        warnings.append(
            f"Warcraft Logs has no ranked {spec.label} parses for this boss and "
            "difficulty yet."
        )

    catalog = spell_index(spec_key)

    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
    results = await asyncio.gather(
        *(
            _player(rank, entry, catalog, spec_key, semaphore)
            for rank, entry in enumerate(rankings, start=1)
        ),
        return_exceptions=True,
    )

    kept: list[dict] = []
    # group key -> toggle id -> the toggle entry, merged across all ten players.
    discovered: dict[str, dict[int, dict]] = {TRINKET_GROUP: {}, POTION_GROUP: {}}
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
        for group_key, entries in found.items():
            for toggle, spell in entries.items():
                discovered[group_key].setdefault(toggle, spell)

    # The ruler has to span the longest pull, otherwise the slowest kill runs off it.
    max_duration = max((p["duration"] for p in kept), default=0.0)

    return {
        "encounter": {"id": encounter_id, "name": encounter_name},
        "difficulty": DIFFICULTY_BY_ID.get(
            difficulty, {"id": difficulty, "name": str(difficulty), "short": "?"}
        ),
        "spec": {"key": spec.key, "label": spec.label, "role": spec.role},
        "maxDuration": max_duration,
        "players": kept,
        # The catalog groups, with the discovered ones filled in from this board.
        "groups": _groups(spec_key, discovered),
        "warnings": warnings,
    }


def _groups(spec_key: str, discovered: dict[str, dict[int, dict]]) -> list[dict]:
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
        found = discovered.get(group.key)
        if found:
            spells.extend(
                sorted(found.values(), key=lambda s: s["name"] or str(s["id"]))
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
    encounter_id: int, difficulty: int, spec
) -> tuple[list[dict], str]:
    variables = {
        "encounterId": encounter_id,
        "difficulty": difficulty,
        "className": spec.class_name,
        "specName": spec.spec_name,
        # Healers rank by healing. Asking for the top Preservation Evokers by damage
        # would return a real list of the wrong people.
        "metric": spec.metric,
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


def _trinket_lookup(equipped: list[dict]) -> tuple[dict, dict]:
    """Icon and name indexes, so a cast can be traced back to the item that fired it."""
    by_icon, by_name = {}, {}
    for item in equipped:
        if item.get("icon"):
            by_icon[_norm_icon(item["icon"])] = item
        if item.get("name"):
            by_name[item["name"].lower()] = item
    return by_icon, by_name


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
    spec_key: str,
    semaphore: asyncio.Semaphore,
) -> tuple[dict, dict[str, dict[int, dict]]]:
    report = entry.get("report") or {}
    code = report.get("code")
    fight_id = report.get("fightID")
    name = entry.get("name") or "Unknown"
    if not code or fight_id is None:
        raise ValueError("ranking carries no report reference")
    if name == ANONYMOUS:
        # Warcraft Logs hides the name when a player opts out of rankings, and every
        # cast lookup here filters on source.name. Without a name there is nothing to
        # filter on, so the row would render empty and look like a player who pressed
        # nothing. Drop it and say why instead. About 3% of ranked parses.
        raise ValueError("the player is anonymous on Warcraft Logs, so their casts "
                         "cannot be looked up")

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
        # Read off the log's own ability icons, falling back to the entry IDs
        # configured on the spec. Neither costs an extra query.
        "heroTree": fight["hero"] and _hero_payload(fight["hero"]["name"]) or _hero(spec_key, entry),
        # source= focuses the log on this player, which is the whole reason to open
        # it: their gear and their talents, rather than the raid-wide summary.
        "reportUrl": _report_url(code, int(fight_id), fight["actor_id"]),
        "casts": fight["casts"],
    }
    return player, fight["discovered"]


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

    by_icon, by_name = _trinket_lookup(equipped)

    events = ((report.get("events") or {}).get("data")) or []
    casts: list[dict] = []
    # Every icon this player's abilities carry. Hero talent abilities are named for
    # their tree, so this doubles as the hero tree evidence at no extra cost.
    icons_seen: list[str] = []
    found: dict[str, dict[int, dict]] = {TRINKET_GROUP: {}, POTION_GROUP: {}}
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
        if icon:
            icons_seen.append(icon)

        known = ability_id in catalog
        item = None
        if not known:
            # Gear first: Freightrunner's Flask is a trinket with an alchemy icon, so
            # the potion heuristic below would otherwise claim it.
            item = by_icon.get(_norm_icon(icon)) or by_name.get(ability_name.lower())

        if known:
            toggle = ability_id
            display_icon = icon
        elif item is not None:
            # Toggled and labelled as the trinket, not as whatever the ability that
            # fired it happens to be called.
            toggle = _trinket_toggle(item["id"])
            display_icon = item["icon"]
            found[TRINKET_GROUP].setdefault(
                toggle,
                {
                    "id": toggle,
                    "name": item["name"] or f"Trinket {item['id']}",
                    "short": _short(item["name"]),
                    "icon": item["icon"],
                    "onByDefault": False,
                },
            )
        elif _is_potion(ability_name, icon):
            toggle = ability_id
            display_icon = icon
            found[POTION_GROUP].setdefault(
                toggle,
                {
                    "id": toggle,
                    "name": ability_name or f"Consumable {ability_id}",
                    "short": _short(ability_name),
                    "icon": icon,
                    "onByDefault": False,
                },
            )
        else:
            # Builders, spenders and everything else the fight is full of.
            continue

        casts.append(
            {
                "spellId": ability_id,
                # What the toggle row switches on. Differs from spellId only for
                # trinkets, where several abilities share one item.
                "toggle": toggle,
                "t": round((float(event["timestamp"]) - start) / 1000.0, 1),
                "name": item["name"] if item is not None else ability_name,
                "icon": display_icon,
            }
        )

    casts.sort(key=lambda c: c["t"])

    return {
        "duration": round((end - start) / 1000.0, 1),
        "kill": bool(fight.get("kill")),
        "casts": casts,
        "actor_id": actor_id,
        "discovered": found,
        "hero": herotalents.from_icons(icons_seen),
    }


def _hero_payload(name: str) -> dict:
    return {"name": name, "short": _short(name), "asset": f"hero/{hero_slug(name)}.png"}


def _hero(spec_key: str, entry: dict) -> dict | None:
    talent_ids = {t["talentID"] for t in (entry.get("talents") or []) if "talentID" in t}
    tree = hero_tree_for(spec_key, talent_ids)
    if tree is None:
        return None
    return {
        "name": tree.name,
        "short": tree.short or _short(tree.name),
        # A static asset we ship, keyed by the tree's name. tools/assets.py fetches
        # the art for every hero tree in the game, so this resolves for any spec.
        "asset": f"hero/{hero_slug(tree.name)}.png" if tree.name else "",
    }


def _is_potion(name: str, icon: str) -> bool:
    """A consumable, by the icon families and names that show up in real parses.

    Checked only after the gear match, since a trinket can carry an alchemy icon.
    """
    slug = _norm_icon(icon)
    if any(hint in slug for hint in POTION_ICON_HINTS):
        return True
    lowered = name.lower()
    return any(hint in lowered for hint in POTION_NAME_HINTS)


def _trinket_toggle(item_id: int) -> int:
    """Trinket toggles live in negative ID space, where no spell ID can collide."""
    return -item_id


def _short(name: str) -> str:
    """A 2-3 character badge, the fallback when an icon will not load."""
    words = [w for w in name.replace("-", " ").split() if w[:1].isalnum()]
    if len(words) >= 2:
        return "".join(w[0] for w in words[:3]).upper()
    return (name[:3] or "?").title()


def _filter_expression(source_name: str) -> str:
    escaped = source_name.replace('"', '\\"')
    return f'source.name = "{escaped}"'


def _report_url(code: str, fight_id: int, actor_id: int | None) -> str:
    base = f"https://www.warcraftlogs.com/reports/{code}?fight={fight_id}"
    return f"{base}&source={actor_id}" if actor_id is not None else base


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
