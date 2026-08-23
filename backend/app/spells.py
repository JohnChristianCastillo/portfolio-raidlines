"""The tracked-spell catalog: what Raidline is allowed to draw on a timeline.

The file to edit when a season changes. Nothing else knows which spells exist:
adding one here makes it a toggle in the UI and fetches it from Warcraft Logs,
removing it drops it from both. Group order is toggle-row order.

Fields per spell:
  id     in-game spell ID, from the wowhead URL /spell=185313/shadow-dance. What the
         API filters on and what the MRT export carries, so it has to be exact.
         Verify new ones with tools/discover.py; a wrong ID matches nothing silently.
  name   display name, shown in tooltips and next to toggles.
  short  2-3 letter badge, drawn when the icon does not load.
  icon   wowhead icon slug. A fallback only: live timelines use the icon Warcraft
         Logs reports, which tracks the current build.
  on_by_default
         whether the toggle starts enabled. Keep this to a couple of spells.
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
# A second spec is a second entry in CATALOG, nothing else.

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
            # Not 282449, which logs also call Secret Technique: that is the clone
            # strikes, so it would draw every use twice.
            Spell(280719, "Secret Technique", "ST", "ability_rogue_sinistercalling"),
        ],
    ),
    SpellGroup(
        key="potions",
        label="Potions",
        color="#3fb950",
        spells=[
            Spell(
                1236994,
                "Potion of Recklessness",
                "POR",
                "inv_12_profession_alchemy_voidpotion_red",
                on_by_default=True,
            ),
            # TODO: other offensive potions of the active season.
        ],
    ),
    SpellGroup(
        key="trinkets",
        label="Trinkets",
        color="#e3a008",
        spells=[
            # TODO: on-use trinkets worth watching this season.
        ],
    ),
]


CATALOG: dict[str, list[SpellGroup]] = {
    "rogue-subtlety": SUBTLETY_ROGUE,
}

# The className/specName pair the rankings query expects, per catalog key.
SPEC_QUERY_NAMES: dict[str, tuple[str, str]] = {
    "rogue-subtlety": ("Rogue", "Subtlety"),
}

# Singular, always, even though the page shows ten of them.
SPEC_LABELS: dict[str, str] = {
    "rogue-subtlety": "Subtlety Rogue",
}


def groups_for(spec_key: str) -> list[SpellGroup]:
    return CATALOG.get(spec_key, [])


def spells_for(spec_key: str) -> list[Spell]:
    """Every tracked spell of a spec, flattened. The fetch set: one events query
    pulls all of them, so toggling in the UI filters data already held."""
    return [s for group in groups_for(spec_key) for s in group.spells]


def spell_ids_for(spec_key: str) -> list[int]:
    return [s.id for s in spells_for(spec_key)]


def spell_index(spec_key: str) -> dict[int, Spell]:
    return {s.id: s for s in spells_for(spec_key)}
