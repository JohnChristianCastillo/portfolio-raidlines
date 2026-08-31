"""Tooltip text for the spells and items a board draws.

Warcraft Logs gives a name and an icon; neither says what an ability does. Blizzard's
Game Data API says, in finished prose, which is what a hover tooltip needs.

Coverage is not total, and the gap is structural rather than a bug to fix:

  class abilities   /data/wow/spell/{id}   works, for most of them
  trinkets          /data/wow/item/{id}    works, and gives the "Use:" line
  potions           nothing                they are item effects whose item ID we
                                           never learn, and Blizzard's item search
                                           cannot find them by name
  boss abilities    nothing                not in the spell endpoint at all

Around a sixth of player abilities have no spell entry either, old and new alike:
Stampeding Roar and Alter Time as much as Void Metamorphosis. There is no second
source to fall back on. Three were checked and each is a dead end:

  /data/wow/search/spell     the index is empty; even an unfiltered query with no
                             criteria returns zero documents
  /data/wow/journal-encounter  names every boss ability and gives each a spell ID,
                             but the sections carrying a spell have empty body_text,
                             and those spell IDs 404 on the spell endpoint anyway
  /data/wow/search/item      cannot find potions by name

So some tooltips are a name and an icon with no body. That is honest and still
useful; inventing text would not be. The UI opens the same card either way, so a
missing description reads as "nothing more to say" rather than as a broken tooltip,
and the boss row fills the space with the add that casts the ability.

Everything here runs at snapshot time. The published site ships the result as one
JSON file and calls Blizzard never.
"""

import logging

from ..blizzard import BlizzardError, Client

log = logging.getLogger(__name__)


def _clean(text: str) -> str:
    """Blizzard wraps descriptions at odd points and uses CRLF."""
    return " ".join((text or "").replace("\r\n", "\n").split())


def for_spells(blizzard: Client, spell_ids: set[int]) -> dict[str, dict]:
    """Descriptions for player abilities, keyed by spell ID as a string.

    String keys because this lands in JSON, where an integer key would be coerced
    anyway, and the frontend looks them up by the same string.
    """
    out: dict[str, dict] = {}
    for spell_id in sorted(spell_ids):
        if spell_id <= 0:
            continue
        try:
            spell = blizzard.spell(spell_id)
        except BlizzardError as exc:
            log.warning("spell %s: %s", spell_id, exc)
            continue
        if not spell:
            continue
        description = _clean(spell.get("description", ""))
        if description:
            out[str(spell_id)] = {
                "name": spell.get("name", ""),
                "description": description,
            }
    return out


def for_items(blizzard: Client, item_ids: set[int]) -> dict[str, dict]:
    """Descriptions for trinkets, keyed by the negative toggle ID the board uses.

    Trinkets are toggled by item rather than by ability, so the key here matches the
    toggle rather than any spell: see _trinket_toggle in the timeline service.
    """
    out: dict[str, dict] = {}
    for item_id in sorted(item_ids):
        try:
            item = blizzard.get(f"/data/wow/item/{item_id}", cache_key=f"item_{item_id}")
        except BlizzardError as exc:
            log.warning("item %s: %s", item_id, exc)
            continue
        if not item:
            continue

        preview = item.get("preview_item") or {}
        # An on-use trinket puts its effect under spells; the rest carry a plain
        # description. Take whichever is there, preferring the use effect.
        parts = [
            _clean(entry.get("description", ""))
            for entry in (preview.get("spells") or [])
        ]
        text = " ".join(p for p in parts if p) or _clean(
            (preview.get("description") or "")
        )
        if text:
            out[str(-item_id)] = {"name": item.get("name", ""), "description": text}
    return out
