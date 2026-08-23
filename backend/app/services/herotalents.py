"""Working out which hero talent tree a parse ran, from its ability icons.

Warcraft Logs reports which talent entries a player took but never which hero tree
those entries belong to, and Blizzard's API has no field for it either: the per-tree
endpoint 404s, and a spec's talent tree carries no hero talent nodes. The game
stores the choice in a hidden SubTreeSelection node that neither API exposes.

What does survive into a log is Blizzard's icon naming. Hero talent abilities are
named for their tree and class:

    inv_ability_deathstalkerrogue_deathstalkersmark
    inv_ability_deathbringerdeathknight_reapersmark
    inv_ability_conduitofthecelestialsmonk_celestialconduit

So a parse is attributed by looking for that shape among the abilities it used.
Checked against every icon in the cache, the strict prefix identifies 30 distinct
trees with no false positives. Loose substring matching does not: "Archon" matches
inv_120_raid_m-archon-queldanas, and "Templar" matches the ancient Templar's Verdict.
Hence the anchored pattern rather than a contains-check.

Two things this cannot do. A tree whose abilities are entirely passive may never
appear in a cast log, and a player who used none of their hero abilities during a
fight looks the same as one who has no tree. Both come back as None, and the caller
falls back to the hand-configured entry IDs on the spec.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "hero_trees.json"

# Class names as they appear inside an icon slug: lowercase, no spaces.
CLASSES = (
    "deathknight",
    "demonhunter",
    "druid",
    "evoker",
    "hunter",
    "mage",
    "monk",
    "paladin",
    "priest",
    "rogue",
    "shaman",
    "warlock",
    "warrior",
)

# inv_ability_<tree><class>_<ability>. Anchored at the start on purpose; see above.
PATTERN = re.compile(r"^inv_ability_([a-z0-9]+?)(" + "|".join(CLASSES) + r")_")


@lru_cache(maxsize=1)
def _trees() -> dict[str, dict]:
    """Tree name lookup, keyed by the squashed name that appears in a slug.

    Written by tools/assets.py from Blizzard's list, so this needs no network.
    """
    if not DATA.is_file():
        return {}
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def from_icon(icon: str) -> dict | None:
    """The hero tree an ability icon belongs to, if it names one."""
    slug = (icon or "").rsplit(".", 1)[0].lower()
    match = PATTERN.match(slug)
    if not match:
        return None
    return _trees().get(match.group(1))


def from_icons(icons) -> dict | None:
    """The first hero tree found among a parse's ability icons.

    First rather than most common: a parse only ever has one hero tree, so a single
    unambiguous hit settles it, and counting would just be slower.
    """
    for icon in icons:
        tree = from_icon(icon)
        if tree:
            return tree
    return None
