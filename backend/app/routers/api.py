"""The data API, all under /api so the gateway can gate it separately from the SPA.

  GET /api/meta        specs, difficulties and the tracked-spell catalog
  GET /api/zones       raid tiers and their bosses, newest first
  GET /api/timelines   the actual product: top N parses and their cooldown usage
  GET /api/budget      remaining Warcraft Logs point budget (diagnostics)

Nothing here is owner-gated. Raidline reads public ranking data and holds no user
data of its own, so every surface is readable by any admitted session.
"""

from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..spells import CATALOG, SPEC_LABELS, groups_for
from ..services import catalog, timeline
from ..wcl import client

router = APIRouter(prefix="/api")


@router.get("/meta")
def meta() -> dict:
    """Everything the UI needs to draw its controls before any boss is chosen."""
    return {
        # live=false means the app is replaying recorded fixtures. The UI says so
        # rather than pretending stale data is current.
        "live": settings.live_enabled,
        "topN": settings.top_n,
        "difficulties": catalog.DIFFICULTIES,
        "specs": [
            {
                "key": key,
                "label": SPEC_LABELS.get(key, key),
                "groups": [
                    {
                        "key": g.key,
                        "label": g.label,
                        "color": g.color,
                        "spells": [
                            {
                                "id": s.id,
                                "name": s.name,
                                "short": s.short,
                                "icon": s.icon,
                                "onByDefault": s.on_by_default,
                            }
                            for s in g.spells
                        ],
                    }
                    for g in groups_for(key)
                ],
            }
            for key in CATALOG
        ],
    }


@router.get("/zones")
async def zones() -> list[dict]:
    try:
        return await catalog.zones()
    except client.WclError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/timelines")
async def timelines(
    encounter: int = Query(..., description="Warcraft Logs encounter (boss) ID"),
    difficulty: int = Query(..., description="3 Normal, 4 Heroic, 5 Mythic"),
    spec: str = Query("rogue-subtlety", description="catalog key, e.g. rogue-subtlety"),
) -> dict:
    if difficulty not in catalog.DIFFICULTY_BY_ID:
        raise HTTPException(status_code=400, detail=f"unsupported difficulty {difficulty}")
    try:
        return await timeline.build(encounter, difficulty, spec)
    except timeline.UnknownSpec as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except client.WclError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/budget")
async def budget() -> dict:
    """How much of the hourly point allowance is left. Handy while developing, since
    an exhausted budget and a broken query look identical from the UI otherwise."""
    try:
        return await client.rate_limit()
    except client.WclError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
