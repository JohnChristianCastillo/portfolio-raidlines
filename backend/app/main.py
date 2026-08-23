"""Raidline: read how the best parses spend their cooldowns, then copy the timing.

Inspired by lorrgs.io, deliberately narrower. Pick a boss, a difficulty and a spec;
the top parses on Warcraft Logs are laid out as one timeline per player so their
cooldown usage can be compared at a glance, and any row can be exported as a Method
Raid Tools reminder string to paste into the game.

Surfaces (one app, behind the gateway at /raidline):
  - the timeline board (public: everything, no owner-only surface exists)

Endpoints (data API under /api so the gateway gates it distinctly from the SPA):
  GET /health         direct/container health (ungated)
  GET /api/meta       specs, difficulties, tracked-spell catalog
  GET /api/zones      raid tiers and bosses
  GET /api/timelines  top N parses and their casts
  GET /api/budget     Warcraft Logs rate-limit budget
Static: /  the built SPA (production only; in dev Vite serves it).

Without Warcraft Logs credentials the app runs on recorded fixtures rather than
failing, so it is testable and demoable offline. /api/meta reports which mode it is
in and the UI labels itself accordingly.
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import api

logging.basicConfig(level=logging.INFO)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "live": settings.live_enabled}


app.include_router(api.router)


# Serve the built SPA (production). Mounted last so /health and /api win first. In dev
# this is unset and Vite serves the SPA instead.
if settings.static_dir and Path(settings.static_dir).is_dir():
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="spa")
