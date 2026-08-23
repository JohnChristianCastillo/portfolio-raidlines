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
class HeroTree:
    """A hero talent tree, identified by the entry ID of its root node.

    A spec's talent pane is three trees: class on the left, specialisation on the
    right, and the hero tree in the middle. The middle one offers a choice of two,
    and the root node of each is unique to it, so its entry ID identifies the tree.

    entry_id  the root node's entry ID, which is what a ranking's talents list
              carries as talentID. NOT the node ID and NOT the spell ID.
    name      display name, e.g. Deathstalker. Blank means unidentified, and nothing
              is drawn rather than something wrong.
    short     2-3 letter badge, drawn when there is no icon.
    icon      wowhead icon slug. Optional.
    """

    entry_id: int
    name: str
    short: str = ""
    icon: str = ""


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

# Hero talent trees per spec, keyed by the entry ID of each tree's root node.
#
# These cannot be derived from the API: Warcraft Logs reports which talent entries a
# player took but never which tree they belong to, and the schema has no field for
# it. Nor can they be inferred statistically. An earlier attempt picked the most
# evenly split mutually exclusive pair of nodes and got an ordinary either/or talent
# choice instead, because a hero tree is not necessarily a close-run thing: every one
# of 232 sampled Subtlety parses runs Deathstalker.
#
# So they are read off the game's talent pane by hand. For a new spec, find the two
# root nodes of the middle tree and take their entry IDs. tools/herotrees.py checks
# a configured pair against live parses and reports anything it fails to classify.
#
# TODO(owner): icon slugs, if the initials badge is not good enough.
HERO_TREES: dict[str, list[HeroTree]] = {
    "rogue-subtlety": [
        # root node Deathstalker's Mark (node 95137, spell 467052)
        HeroTree(117733, "Deathstalker", short="DS"),
        # root node Unseen Blade (node 95140, spell 441146)
        HeroTree(117737, "Trickster", short="TR"),
    ],
}


def hero_tree_for(spec_key: str, talent_ids: set[int]) -> HeroTree | None:
    """Which hero tree a player's talent list indicates, if it is a named one."""
    for tree in HERO_TREES.get(spec_key, []):
        if tree.entry_id in talent_ids and tree.name:
            return tree
    return None

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
