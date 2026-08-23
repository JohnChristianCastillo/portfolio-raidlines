"""The tracked-spell catalog: what Raidline is allowed to draw on a timeline.

Adding a spell here makes it a toggle in the UI, removing it drops it. Group order
is toggle-row order.

Only the hand-curated groups live here. Potions and trinkets are discovered per
board from what the ranked players actually used, so they stay empty and need no
attention when a season turns over.

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

    entry_id   the root node's entry ID, which is what a ranking's talents list
               carries as talentID. NOT the node ID and NOT the spell ID.
    name       display name, e.g. Deathstalker. Blank means unidentified, and
               nothing is drawn rather than something wrong.
    short      2-3 letter badge, drawn when there is no icon.
    root_spell the root node's spell ID. Blizzard exposes no icon for a hero talent
               tree, so the tree is drawn with its root ability's icon, which is what
               a player recognises it by anyway.
    icon_slug  unused for art now that tools/assets.py fetches the tree's own icon
               by name. Kept as a fallback hook for a tree the wiki lacks.
    """

    entry_id: int
    name: str
    short: str = ""
    root_spell: int = 0
    icon_slug: str = ""


@dataclass(frozen=True)
class SpellGroup:
    key: str
    label: str
    color: str  # timeline pill colour, also the toggle's accent
    spells: list[Spell] = field(default_factory=list)


@dataclass(frozen=True)
class Spec:
    """A playable specialisation Raidline can draw a board for.

    key         our slug, used in URLs and as the catalog key
    label       display name, singular
    class_name  className as the Warcraft Logs rankings query spells it
    spec_name   specName, likewise
    spec_id     Blizzard playable-specialization ID. Warcraft Logs reports it as
                specID in combatantInfo, and it is what the spec icon is fetched by
    role        dps, healer or tank. Decides the ranking metric, see below
    groups      the tracked-spell catalog for this spec
    hero_trees  the two hero talent trees, by root node entry ID
    """

    key: str
    label: str
    class_name: str
    spec_name: str
    spec_id: int
    role: str
    groups: list[SpellGroup] = field(default_factory=list)
    hero_trees: list[HeroTree] = field(default_factory=list)

    @property
    def metric(self) -> str:
        """What Warcraft Logs should rank this spec by.

        Healers are ranked by healing, not damage: the top twenty Preservation
        Evokers by DPS would be a meaningless list. Tanks stay on dps, which is how
        Warcraft Logs itself ranks them.
        """
        return "hps" if self.role == "healer" else "dps"


# Hero talent trees are keyed by the entry ID of each tree's root node.
#
# These cannot be derived from the API: Warcraft Logs reports which talent entries a
# player took but never which tree they belong to, and the schema has no field for
# it. Nor can they be inferred statistically. An earlier attempt picked the most
# evenly split mutually exclusive pair of nodes and got an ordinary either/or talent
# choice instead, because a hero tree is not necessarily a close-run thing: every one
# of 232 sampled Subtlety parses runs Deathstalker.
#
# So they are read off the game's talent pane by hand: the middle of the three trees
# is the hero tree, and the entry ID of each of its two root nodes names it.
# tools/herotrees.py checks a configured pair against live parses.


# --- the catalogs ---------------------------------------------------------------
#
# Every spell ID below was resolved with tools/catalog.py, which reads them out of
# real ranked parses rather than trusting a typed list. Nothing here is from memory.
#
# Class abilities are shared between a class's specs: an ability's ID does not change
# between them, verified for Anti-Magic Zone across Frost and Unholy. Where a spec
# genuinely differs it gets its own entry, as with Ascendance, which is 114051 for
# Enhancement and 114050 for Elemental.

DEFENSIVE = "#4aa3df"
MAIN = "#a259e6"
POTION = "#3fb950"
TRINKET = "#e3a008"


def _groups(defensives: list[Spell], main: list[Spell]) -> list[SpellGroup]:
    """The four groups every spec has, in toggle-row order.

    Potions and trinkets are always empty here: both are discovered per board from
    what the ranked players actually used, so they need no maintenance.
    """
    return [
        SpellGroup("defensives", "Defensives", DEFENSIVE, defensives),
        SpellGroup("main", "Main abilities", MAIN, main),
        SpellGroup("potions", "Potions", POTION, []),
        SpellGroup("trinkets", "Trinkets", TRINKET, []),
    ]


ROGUE_DEFENSIVES = [
    Spell(1856, "Vanish", "Van", "ability_vanish"),
    Spell(1966, "Feint", "Fnt", "ability_rogue_feint"),
    Spell(5277, "Evasion", "Eva", "spell_shadow_shadowward"),
    Spell(31224, "Cloak of Shadows", "Clk", "spell_shadow_nethercloak"),
    Spell(185311, "Crimson Vial", "CV", "ability_rogue_crimsonvial"),
]

DEATH_KNIGHT_DEFENSIVES = [
    Spell(48265, "Death's Advance", "DA", "spell_shadow_demonicempathy"),
    Spell(48707, "Anti-Magic Shell", "AMS", "spell_shadow_antimagicshell"),
    Spell(48792, "Icebound Fortitude", "IF", "spell_deathknight_iceboundfortitude"),
    Spell(49039, "Lichborne", "Lic", "spell_shadow_raisedead"),
    Spell(51052, "Anti-Magic Zone", "AMZ", "spell_deathknight_antimagiczone"),
]

SHAMAN_DEFENSIVES = [
    Spell(108271, "Astral Shift", "AS", "ability_shaman_astralshift"),
    Spell(192077, "Wind Rush Totem", "WRT", "ability_shaman_windwalktotem"),
    Spell(198103, "Earth Elemental", "EE", "spell_nature_earthelemental_totem"),
]

# Reaper's Mark comes from the Deathbringer hero tree, so it appears only for death
# knights who took it. Verified on Frost; no Unholy parse in a sample of fifteen used
# it, which is a talent choice rather than a wrong ID.
REAPERS_MARK = Spell(
    439843, "Reaper's Mark", "RM", "inv_ability_deathbringerdeathknight_reapersmark"
)


SPECS: dict[str, Spec] = {
    # --- Rogue ----------------------------------------------------------------------
    "rogue-subtlety": Spec(
        key="rogue-subtlety",
        label="Subtlety Rogue",
        class_name="Rogue",
        spec_name="Subtlety",
        spec_id=261,
        role="dps",
        groups=_groups(
            ROGUE_DEFENSIVES,
            [
                Spell(121471, "Shadow Blades", "SB", "inv_knife_1h_grimbatolraid_d_03", on_by_default=True),
                Spell(185313, "Shadow Dance", "SD", "ability_rogue_shadowdance", on_by_default=True),
                # Not 282449, which logs also call Secret Technique: that one is the
                # clone strikes, so tracking it would draw every use twice.
                Spell(280719, "Secret Technique", "ST", "ability_rogue_sinistercalling"),
            ],
        ),
        hero_trees=[
            HeroTree(117733, "Deathstalker", short="DS"),
            HeroTree(117737, "Trickster", short="TR"),
        ],
    ),
    "rogue-assassination": Spec(
        key="rogue-assassination",
        label="Assassination Rogue",
        class_name="Rogue",
        spec_name="Assassination",
        spec_id=259,
        role="dps",
        groups=_groups(
            ROGUE_DEFENSIVES,
            [
                Spell(360194, "Deathmark", "Dth", "ability_rogue_deathmark", on_by_default=True),
                Spell(385627, "Kingsbane", "Kng", "inv_knife_1h_artifactgarona_d_01", on_by_default=True),
                Spell(5938, "Shiv", "Shv", "inv_throwingknife_04"),
            ],
        ),
    ),
    "rogue-outlaw": Spec(
        key="rogue-outlaw",
        label="Outlaw Rogue",
        class_name="Rogue",
        spec_name="Outlaw",
        spec_id=260,
        role="dps",
        groups=_groups(
            ROGUE_DEFENSIVES,
            [
                Spell(13750, "Adrenaline Rush", "AR", "spell_shadow_shadowworddominate", on_by_default=True),
                Spell(381989, "Keep It Rolling", "KIR", "ability_rogue_keepitrolling", on_by_default=True),
                Spell(51690, "Killing Spree", "KS", "inv_112_rogue_betweentheeyes"),
            ],
        ),
    ),
    # --- Death Knight -----------------------------------------------------------------
    "deathknight-frost": Spec(
        key="deathknight-frost",
        label="Frost Death Knight",
        class_name="DeathKnight",
        spec_name="Frost",
        spec_id=251,
        role="dps",
        groups=_groups(
            DEATH_KNIGHT_DEFENSIVES,
            [
                Spell(51271, "Pillar of Frost", "PoF", "ability_deathknight_pillaroffrost", on_by_default=True),
                Spell(1249658, "Breath of Sindragosa", "BoS", "spell_deathknight_breathofsindragosa", on_by_default=True),
                Spell(1265384, "Frostwyrm's Fury", "FF", "inv12_apextalent_deathknight_chosenofthefrostbrood"),
                Spell(46585, "Raise Dead", "RD", "inv_pet_ghoul"),
                REAPERS_MARK,
            ],
        ),
    ),
    "deathknight-unholy": Spec(
        key="deathknight-unholy",
        label="Unholy Death Knight",
        class_name="DeathKnight",
        spec_name="Unholy",
        spec_id=252,
        role="dps",
        groups=_groups(
            DEATH_KNIGHT_DEFENSIVES,
            [
                Spell(42650, "Army of the Dead", "AotD", "spell_deathknight_armyofthedead", on_by_default=True),
                Spell(1233448, "Dark Transformation", "DT", "achievement_boss_festergutrotface", on_by_default=True),
                REAPERS_MARK,
            ],
        ),
    ),
    # --- Shaman -----------------------------------------------------------------------
    "shaman-enhancement": Spec(
        key="shaman-enhancement",
        label="Enhancement Shaman",
        class_name="Shaman",
        spec_name="Enhancement",
        spec_id=263,
        role="dps",
        groups=_groups(
            SHAMAN_DEFENSIVES,
            [
                # Warcraft Logs reports Ascendance's icon as a bare number rather than
                # a slug, so it is left blank and the short badge is drawn instead.
                Spell(114051, "Ascendance", "Asc", "", on_by_default=True),
                Spell(469270, "Doom Winds", "DW", "ability_ironmaidens_swirlingvortex", on_by_default=True),
            ],
        ),
    ),
    "shaman-elemental": Spec(
        key="shaman-elemental",
        label="Elemental Shaman",
        class_name="Shaman",
        spec_name="Elemental",
        spec_id=262,
        role="dps",
        groups=_groups(
            SHAMAN_DEFENSIVES,
            [
                Spell(114050, "Ascendance", "Asc", "", on_by_default=True),
                Spell(191634, "Stormkeeper", "SK", "ability_thunderking_lightningwhip", on_by_default=True),
            ],
        ),
    ),
}


def hero_slug(name: str) -> str:
    """Filename key for a hero tree's art, matching tools/assets.py."""
    out = "".join(c.lower() if c.isalnum() else "-" for c in name)
    return "-".join(filter(None, out.split("-")))


def spec_for(spec_key: str) -> Spec | None:
    return SPECS.get(spec_key)


def hero_tree_for(spec_key: str, talent_ids: set[int]) -> HeroTree | None:
    """Which hero tree a player's talent list indicates, if it is a named one."""
    spec = SPECS.get(spec_key)
    if spec is None:
        return None
    for tree in spec.hero_trees:
        if tree.entry_id in talent_ids and tree.name:
            return tree
    return None


def groups_for(spec_key: str) -> list[SpellGroup]:
    spec = SPECS.get(spec_key)
    return spec.groups if spec else []


def spells_for(spec_key: str) -> list[Spell]:
    """Every tracked spell of a spec, flattened. The fetch set: one events query
    pulls all of them, so toggling in the UI filters data already held."""
    return [s for group in groups_for(spec_key) for s in group.spells]


def spell_ids_for(spec_key: str) -> list[int]:
    return [s.id for s in spells_for(spec_key)]


def spell_index(spec_key: str) -> dict[int, Spell]:
    return {s.id: s for s in spells_for(spec_key)}
