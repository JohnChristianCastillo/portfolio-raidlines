"""Record real Warcraft Logs responses as fixtures.

    python tools/capture.py --encounter 3470 --difficulty 5

Needs credentials in backend/.env. Writes the same file names the fixture reader
expects, so whatever is captured here is exactly what the app replays with the
credentials removed.

Why bother, when live mode exists: it makes the app demoable on a machine with no
API client at all, it makes UI work free against the hourly point budget, and it
pins down real response shapes. The generated demo fixtures are a stand-in until
this has been run once.

Captured files are real ranking data and are not committed. See .gitignore.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Same reason as in discover.py: player names are often not Latin-1 and the Windows
# console is cp1252 by default.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.config import settings  # noqa: E402
from app.spells import spec_for  # noqa: E402
from app.services import timeline  # noqa: E402
from app.wcl import client, queries  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "app" / "fixtures"


async def capture(encounter: int, difficulty: int, spec_key: str, top_n: int) -> None:
    spec = spec_for(spec_key)
    if spec is None:
        raise SystemExit(f"unknown spec {spec_key!r}")

    zones_data = await client.graphql(
        queries.ZONES, {}, cache_kind="zones", cache_ttl=settings.catalog_ttl_seconds
    )
    _write("zones", zones_data)

    ranking_vars = {
        "encounterId": encounter,
        "difficulty": difficulty,
        "className": spec.class_name,
        "specName": spec.spec_name,
        "metric": spec.metric,
        "page": 1,
    }
    rankings_data = await client.graphql(
        queries.RANKINGS,
        ranking_vars,
        cache_kind="rankings",
        cache_ttl=settings.rankings_ttl_seconds,
    )
    _write(client.fixture_name("rankings", ranking_vars), rankings_data)

    payload = (
        (rankings_data.get("worldData") or {}).get("encounter") or {}
    ).get("characterRankings") or {}
    rankings = payload if isinstance(payload, list) else payload.get("rankings") or []

    for entry in rankings[:top_n]:
        report = entry.get("report") or {}
        code, fight_id = report.get("code"), report.get("fightID")
        if not code or fight_id is None:
            continue
        fight_vars = {
            "code": code,
            "fightId": int(fight_id),
            "filter": timeline._filter_expression(entry.get("name", "")),
        }
        try:
            fight_data = await client.graphql(
                queries.FIGHT,
                fight_vars,
                cache_kind="fight",
                cache_ttl=settings.events_ttl_seconds,
            )
        except client.WclError as exc:
            print(f"  skipped {entry.get('name')}: {exc}")
            continue
        _write(client.fixture_name("fight", fight_vars), fight_data)

    budget = await client.rate_limit()
    print(f"budget after capture: {budget}")


def _write(name: str, data: dict) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encounter", type=int, required=True, help="boss ID")
    parser.add_argument("--difficulty", type=int, default=5, help="3 N, 4 H, 5 M")
    parser.add_argument("--spec", default="rogue-subtlety")
    parser.add_argument("--top", type=int, default=settings.top_n)
    args = parser.parse_args()

    if not settings.live_enabled:
        raise SystemExit(
            "no Warcraft Logs credentials configured (or RAIDLINE_FORCE_FIXTURES is "
            "set). Nothing to capture. See _local/wcl_api_registration/how_to_setup.md"
        )

    asyncio.run(capture(args.encounter, args.difficulty, args.spec, args.top))


if __name__ == "__main__":
    main()
