"""The tracked-spell catalog: what Raidline is allowed to draw on a timeline.

This is the file to edit when a season changes. Nothing else knows which spells
exist. Adding a spell here makes it appear as a toggle in the UI and be fetched
from Warcraft Logs; removing it makes it vanish from both.

Structure: one CATALOG per spec, split into groups in the order the spec asked for
(defensives, main abilities, potions, trinkets). Group order here is the order the
toggle rows render in.

Fields per spell:
  id     Warcraft Logs / in-game spell ID. This is what the API filters on and what
         the exported MRT string carries, so it has to be exact. Look one up on
         wowhead: the number in the URL /spell=185313/shadow-dance.
  name   Display name, ours to choose. Shown in tooltips and next to toggles.
  short  2-3 letter badge drawn on the timeline pill when no icon loads.
  icon   Wowhead icon slug, used only as a fallback. When a timeline is built from
         live data the icon reported by Warcraft Logs wins, since that is
         authoritative for the current build and this list is hand-maintained.
  on_by_default
         Whether its toggle starts enabled. Keep this small. The spec's own
         screenshots start with one or two spells on, then add more by hand.

Potions and trinkets are deliberately short and marked TODO: per the spec these are
season-specific and get curated by hand rather than listing every trinket in the game.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Spell:
    id: int
    name: str
    short: str
    icon: str = ""
    on_by_default: bool = False


@dataclass(frozen=True)
class SpellGroup:
    key: str
    label: str
    color: str  # timeline pill colour, also the toggle's accent
    spells: list[Spell] = field(default_factory=list)


# --- Subtlety Rogue -----------------------------------------------------------------
# The only spec in the MVP. A second spec is a second entry in CATALOG, nothing else.

SUBTLETY_ROGUE = [
    SpellGroup(
        key="defensives",
        label="Defensives",
        color="#4aa3df",
        spells=[
            Spell(1856, "Vanish", "Van", "ability_vanish"),
            Spell(1966, "Feint", "Fnt", "ability_rogue_feint"),
            Spell(5277, "Evasion", "Eva", "spell_shadow_shadowward"),
            Spell(31224, "Cloak of Shadows", "Clk", "spell_shadow_nethercloak"),
            Spell(185311, "Crimson Vial", "CV", "ability_rogue_crimsonvial"),
        ],
    ),
    SpellGroup(
        key="main",
        label="Main abilities",
        color="#a259e6",
        spells=[
            Spell(121471, "Shadow Blades", "SB", "inv_knife_1h_grimbatolraid_d_03", on_by_default=True),
            Spell(185313, "Shadow Dance", "SD", "ability_rogue_shadowdance", on_by_default=True),
            Spell(280719, "Secret Technique", "ST", "ability_rogue_secrettechnique"),
            Spell(212283, "Symbols of Death", "SoD", "spell_shadow_rune"),
            Spell(381623, "Thistle Tea", "Tea", "inv_drink_milk_05"),
        ],
    ),
    SpellGroup(
        key="potions",
        label="Potions",
        color="#3fb950",
        spells=[
            # TODO(owner): the offensive potions of the active season, starting with
            # Potion of Recklessness.
            #
            # Do not type these IDs from memory. A wrong potion ID does not error, it
            # silently matches nothing and leaves a toggle that draws an empty row
            # forever. Read them off a real log instead:
            #
            #   python tools/discover.py --encounter <boss id> --difficulty 5
            #
            # which prints every ability the top parse actually cast, as catalog
            # lines ready to paste in here.
        ],
    ),
    SpellGroup(
        key="trinkets",
        label="Trinkets",
        color="#e3a008",
        spells=[
            # TODO(owner): the handful of on-use trinkets worth watching this season.
            # Deliberately curated, not every trinket in the game (spec section 1).
            # Same as potions: get the IDs from tools/discover.py, not from memory.
        ],
    ),
]


CATALOG: dict[str, list[SpellGroup]] = {
    "rogue-subtlety": SUBTLETY_ROGUE,
}

# Warcraft Logs wants these as separate className/specName strings on the rankings
# query, so each catalog key maps to the pair the API expects.
SPEC_QUERY_NAMES: dict[str, tuple[str, str]] = {
    "rogue-subtlety": ("Rogue", "Subtlety"),
}

SPEC_LABELS: dict[str, str] = {
    "rogue-subtlety": "Subtlety Rogues",
}


def groups_for(spec_key: str) -> list[SpellGroup]:
    return CATALOG.get(spec_key, [])


def spells_for(spec_key: str) -> list[Spell]:
    """Every tracked spell of a spec, flattened. This is the fetch set: one events
    query pulls all of them at once so that toggling a spell in the UI is a filter
    over data we already hold, not another trip to Warcraft Logs."""
    return [s for group in groups_for(spec_key) for s in group.spells]


def spell_ids_for(spec_key: str) -> list[int]:
    return [s.id for s in spells_for(spec_key)]


def spell_index(spec_key: str) -> dict[int, Spell]:
    return {s.id: s for s in spells_for(spec_key)}
