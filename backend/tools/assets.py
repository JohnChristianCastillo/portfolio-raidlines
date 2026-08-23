"""Fetch the game art Raidline ships: specialisation and hero talent icons.

    python tools/assets.py            # every spec, plus hero icons for configured specs
    python tools/assets.py --spec rogue-subtlety

Writes into frontend/public/assets, which Vite copies verbatim into the build, so
the published page serves its own icons and calls nobody at run time. Downloads are
skipped when the file already exists, making a re-run nearly free.

Two shapes, and the difference is deliberate:

  specs/<specId>.jpg   square, Blizzard's own specialisation icon
  hero/<entryId>.jpg   round in the UI, the icon of the hero tree's root ability

Blizzard exposes no icon for a hero talent tree. The per-tree endpoint is listed in
the index but answers 404, and a spec's talent tree carries no hero talent nodes. So
a tree is drawn with its root ability's icon instead: Deathstalker's Mark for
Deathstalker, Unseen Blade for Trickster, which is what players recognise them by.

Those root spell IDs are hand-configured on HeroTree in spells.py, and they go stale:
the game renumbers spells between expansions, and Deathstalker's Mark already has.
When a root spell no longer resolves, the icon slug Warcraft Logs reports is used
instead, which survives renumbering because it names the art rather than the spell.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.blizzard import BlizzardError, Client  # noqa: E402
from app.spells import SPECS  # noqa: E402

ASSETS = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "assets"
)

# Fallback art host, used only when a root spell has been renumbered away. Fetched
# once at build time into our own assets, never hotlinked at request time.
ICON_CDN = "https://wow.zamimg.com/images/wow/icons/large"


def fetch_spec_icons(blizzard: Client) -> list[dict]:
    """Every playable spec's icon, not just the ones with a catalog.

    All of them, because there are only about forty, they are a few kilobytes each,
    and having the art already present makes adding a spec a catalog edit rather than
    a catalog edit plus remembering to run this again.
    """
    manifest = []
    for entry in sorted(blizzard.specializations(), key=lambda s: s.get("id", 0)):
        spec_id, name = entry.get("id"), entry.get("name")
        if not spec_id:
            continue
        detail = blizzard.specialization(spec_id) or {}
        class_name = (detail.get("playable_class") or {}).get("name", "")
        role = (detail.get("role") or {}).get("type", "")
        url = blizzard.spec_icon(spec_id)
        if not url:
            print(f"  {spec_id:<5} {name:<16} no icon")
            continue
        target = ASSETS / "specs" / f"{spec_id}.jpg"
        fetched = blizzard.download(url, target)
        manifest.append(
            {
                "id": spec_id,
                "name": name,
                "class": class_name,
                "role": role,
                "icon": f"specs/{spec_id}.jpg",
                # Blizzard's own hero tree names, which is the one hero fact the API
                # does give us. The entry IDs that identify them in a log do not
                # come from here; see HeroTree in spells.py.
                "heroTrees": blizzard.hero_trees(spec_id),
            }
        )
        print(
            f"  {spec_id:<5} {class_name + ' ' + str(name):<28} {role:<8} "
            f"{'fetched' if fetched else 'cached'}"
        )
    return manifest


def fetch_hero_icons(blizzard: Client, only: str | None) -> list[dict]:
    manifest = []
    for key, spec in SPECS.items():
        if only and key != only:
            continue
        for tree in spec.hero_trees:
            if not tree.root_spell:
                print(f"  {spec.label} / {tree.name or tree.entry_id}: no root spell set")
                continue
            url = blizzard.spell_icon(tree.root_spell)
            source = f"spell {tree.root_spell}"
            if not url and tree.icon_slug:
                # The root spell has been renumbered out of existence. The slug names
                # the art file, which outlives the spell ID.
                url = f"{ICON_CDN}/{tree.icon_slug}.jpg"
                source = f"slug {tree.icon_slug}"
            if not url:
                print(
                    f"  {spec.label} / {tree.name}: spell {tree.root_spell} has no "
                    "icon and no icon_slug is set"
                )
                continue
            target = ASSETS / "hero" / f"{tree.entry_id}.jpg"
            fetched = blizzard.download(url, target)
            spell = blizzard.spell(tree.root_spell) or {}
            manifest.append(
                {
                    "entryId": tree.entry_id,
                    "spec": key,
                    "name": tree.name,
                    "rootSpell": tree.root_spell,
                    "rootSpellName": spell.get("name", ""),
                    "icon": f"hero/{tree.entry_id}.jpg",
                }
            )
            print(
                f"  {spec.label} / {tree.name:<14} <- {source:<46} "
                f"{'fetched' if fetched else 'cached'}"
            )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", help="limit hero icons to one catalog spec")
    parser.add_argument(
        "--skip-specs", action="store_true", help="hero icons only, skip the spec sweep"
    )
    args = parser.parse_args()

    try:
        with Client() as blizzard:
            specs: list[dict] = []
            if not args.skip_specs:
                print("specialisation icons (square):")
                specs = fetch_spec_icons(blizzard)
            print("\nhero talent icons (round), from each tree's root ability:")
            heroes = fetch_hero_icons(blizzard, args.spec)
    except BlizzardError as exc:
        raise SystemExit(str(exc))

    ASSETS.mkdir(parents=True, exist_ok=True)
    manifest = ASSETS / "manifest.json"
    if args.skip_specs and manifest.is_file():
        # Keep the spec half of an existing manifest when only heroes were refreshed.
        specs = json.loads(manifest.read_text(encoding="utf-8")).get("specs", [])
    manifest.write_text(
        json.dumps({"specs": specs, "heroTrees": heroes}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    total = sum(1 for _ in (ASSETS).rglob("*.jpg"))
    size = sum(p.stat().st_size for p in ASSETS.rglob("*.jpg"))
    print(f"\n{total} icons, {size / 1024:.0f} KB total, under {ASSETS}")
    print(f"manifest: {manifest}")


if __name__ == "__main__":
    main()
