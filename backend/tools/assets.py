"""Fetch the game art Raidline ships: specialisation and hero talent icons.

    python tools/assets.py                # specialisation icons and hero talent icons
    python tools/assets.py --skip-specs   # hero talent icons only

Writes into frontend/public/assets, which Vite copies verbatim into the build, so
the published page serves its own icons and calls nobody at run time. Downloads are
skipped when the file already exists, making a re-run nearly free.

Two shapes, and the difference is deliberate:

  specs/<specId>.jpg   square, Blizzard's own specialisation icon
  hero/<tree-slug>.png round in the UI, the hero talent tree's own art

Blizzard exposes no icon for a hero talent tree: the per-tree endpoint is listed in
its index but answers 404, and a spec's talent tree carries no hero talent nodes.
The dedicated art lives on warcraft.wiki.gg instead, as a category of exactly 41
files named "Hero talent <name>.png", which is the same 41 trees Blizzard's index
names. So the trees are fetched from there and matched to Blizzard's names.

That matters beyond convenience. Matching on name means every hero tree in the game
is covered without configuring anything per spec: adding a spec needs a catalog and
nothing else. The earlier approach drew a tree with its root ability's icon, which
needed a hand-maintained spell ID per tree and broke when the game renumbered one
(Deathstalker's Mark was 467052 in The War Within and no longer resolves). It stays
as a fallback for anything the wiki does not have.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.blizzard import BlizzardError, Client  # noqa: E402

ASSETS = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "assets"
)

# Fallback art host, used only when a root spell has been renumbered away. Fetched
# once at build time into our own assets, never hotlinked at request time.
ICON_CDN = "https://wow.zamimg.com/images/wow/icons/large"

# Hero talent tree art. A MediaWiki API, so this is a documented public interface
# rather than page scraping, and it is polite to identify ourselves.
WIKI_API = "https://warcraft.wiki.gg/api.php"
WIKI_CATEGORY = "Category:WoW_Icons:_Pseudo_TalentFrame"
USER_AGENT = "Raidline/0.1 (personal, non-commercial fan project)"


def slugify(name: str) -> str:
    """A filename-safe key for a hero tree, e.g. Elune's Chosen -> elunes-chosen."""
    out = [c.lower() if c.isalnum() else "-" for c in name]
    return "-".join(filter(None, "".join(out).split("-")))


def wiki_hero_icons() -> dict[str, str]:
    """Every hero talent icon the wiki has, keyed by its normalised tree name."""
    response = httpx.get(
        WIKI_API,
        params={
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": WIKI_CATEGORY,
            "gcmlimit": "500",
            "gcmtype": "file",
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    icons = {}
    for page in ((response.json().get("query") or {}).get("pages") or {}).values():
        title = page.get("title", "")
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("url")
        if not url:
            continue
        # "File:Hero talent mountain thane.png" -> "mountainthane"
        stem = title.removeprefix("File:").removesuffix(".png")
        stem = stem.removeprefix("Hero talent ").strip()
        icons["".join(c for c in stem.lower() if c.isalnum())] = url
    return icons


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


def fetch_hero_icons(blizzard: Client) -> list[dict]:
    """Every hero tree of every spec, from the wiki, matched by name.

    Driven by Blizzard's spec list rather than our own registry, so the art for a
    spec is already present before its catalog is written.
    """
    wiki = wiki_hero_icons()
    print(f"  ({len(wiki)} hero talent icons available on the wiki)")

    manifest = []
    seen: set[str] = set()
    for entry in sorted(blizzard.specializations(), key=lambda s: s.get("id", 0)):
        spec_id = entry.get("id")
        if not spec_id:
            continue
        for tree in blizzard.hero_trees(spec_id):
            name = tree.get("name") or ""
            key = "".join(c for c in name.lower() if c.isalnum())
            if not key or key in seen:
                continue
            seen.add(key)
            url = wiki.get(key)
            if not url:
                print(f"  {name:<26} no wiki icon")
                continue
            slug = slugify(name)
            fetched = _download(url, ASSETS / "hero" / f"{slug}.png")
            manifest.append(
                {
                    "id": tree.get("id"),
                    "name": name,
                    "slug": slug,
                    "icon": f"hero/{slug}.png",
                }
            )
            print(f"  {name:<26} {'fetched' if fetched else 'cached'}")
    return manifest


def _download(url: str, destination: Path) -> bool:
    """Fetch to disk, skipping work when the file is already there."""
    if destination.is_file() and destination.stat().st_size > 0:
        return False
    response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
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
            print("\nhero talent icons (round), from warcraft.wiki.gg:")
            heroes = fetch_hero_icons(blizzard)
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

    art = [p for p in ASSETS.rglob("*") if p.suffix in (".jpg", ".png")]
    total = len(art)
    size = sum(p.stat().st_size for p in art)
    print(f"\n{total} icons, {size / 1024:.0f} KB total, under {ASSETS}")
    print(f"manifest: {manifest}")


if __name__ == "__main__":
    main()
