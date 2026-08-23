"""Blizzard Game Data API, used at build time only.

Warcraft Logs says what happened in a fight. Blizzard says what a spell is called,
what it does and what it looks like. That second half is reference data: it changes
on patch days and never between them, so it is fetched during a build, cached to
disk, and baked into the static output. The published site never calls Blizzard.

Why this rather than scraping Wowhead for tooltips: Blizzard's descriptions come
back as finished prose (verified, not assumed: no unresolved $s1-style variables),
the API is free and sanctioned for fan sites, and it will not break the day someone
changes their page markup.

Auth is the same client-credentials shape as Warcraft Logs, but a different
provider, different token endpoint and a token that lasts a day rather than a year.
"""

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from .config import settings

log = logging.getLogger(__name__)


class BlizzardError(RuntimeError):
    """A Blizzard Game Data request failed."""


class _Token:
    """One access token, cached on disk. Blizzard's last 24 hours."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at = 0.0
        self._path = Path(settings.cache_dir) / "blizzard_token.json"

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._token = payload.get("access_token")
        self._expires_at = payload.get("expires_at", 0.0)

    def get(self, http: httpx.Client) -> str:
        if self._token is None:
            self._load()
        if self._token and time.time() < self._expires_at - 60:
            return self._token

        basic = base64.b64encode(
            f"{settings.blizzard_client_id}:{settings.blizzard_client_secret}".encode()
        ).decode()
        response = http.post(
            settings.blizzard_token_url,
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {basic}"},
        )
        if response.status_code != 200:
            raise BlizzardError(
                f"token request failed ({response.status_code}). Check "
                "RAIDLINES_BLIZZARD_CLIENT_ID / _SECRET."
            )
        payload = response.json()
        self._token = payload["access_token"]
        self._expires_at = time.time() + float(payload.get("expires_in", 86400))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"access_token": self._token, "expires_at": self._expires_at}),
            encoding="utf-8",
        )
        log.info("obtained a new Blizzard token")
        return self._token


_token = _Token()


class Client:
    """A session against the Game Data API, with the JSON responses cached to disk.

    Used as a context manager so one build reuses a single connection pool:

        with Client() as blizzard:
            spell = blizzard.spell(185313)
    """

    def __init__(self, cache_ttl: int = 30 * 24 * 3600) -> None:
        if not settings.blizzard_enabled:
            raise BlizzardError(
                "no Blizzard credentials configured. Set RAIDLINES_BLIZZARD_CLIENT_ID "
                "and RAIDLINES_BLIZZARD_CLIENT_SECRET in backend/.env"
            )
        self._http = httpx.Client(timeout=30.0)
        self._cache_ttl = cache_ttl
        self._dir = Path(settings.cache_dir) / "blizzard"

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc: object) -> None:
        self._http.close()

    # --- plumbing -------------------------------------------------------------------

    def _cached(self, key: str) -> Any | None:
        path = self._dir / f"{key}.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if time.time() - payload.get("stored_at", 0) > self._cache_ttl:
            return None
        return payload.get("data")

    def _store(self, key: str, data: Any) -> None:
        path = self._dir / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"stored_at": time.time(), "data": data}), encoding="utf-8"
        )

    def get(self, path: str, cache_key: str | None = None, **params: Any) -> dict | None:
        """One namespaced GET. Returns None on 404, which is a normal answer here:
        plenty of advertised endpoints simply are not implemented."""
        if cache_key:
            hit = self._cached(cache_key)
            if hit is not None:
                return hit or None

        response = self._http.get(
            f"{settings.blizzard_host}{path}",
            params={
                "namespace": settings.blizzard_namespace,
                "locale": settings.blizzard_locale,
                **params,
            },
            headers={"Authorization": f"Bearer {_token.get(self._http)}"},
        )
        if response.status_code == 404:
            if cache_key:
                self._store(cache_key, {})
            return None
        if response.status_code != 200:
            raise BlizzardError(f"{path} returned {response.status_code}")

        data = response.json()
        if cache_key:
            self._store(cache_key, data)
        return data

    # --- the bits Raidlines actually wants -------------------------------------------

    def spell(self, spell_id: int) -> dict | None:
        """Name and description. The description is what the tooltip shows."""
        return self.get(f"/data/wow/spell/{spell_id}", cache_key=f"spell_{spell_id}")

    def spell_icon(self, spell_id: int) -> str | None:
        return self._first_asset(
            self.get(
                f"/data/wow/media/spell/{spell_id}", cache_key=f"spell_media_{spell_id}"
            )
        )

    def specializations(self) -> list[dict]:
        data = self.get(
            "/data/wow/playable-specialization/index", cache_key="spec_index"
        )
        return (data or {}).get("character_specializations") or []

    def specialization(self, spec_id: int) -> dict | None:
        return self.get(
            f"/data/wow/playable-specialization/{spec_id}", cache_key=f"spec_{spec_id}"
        )

    def spec_icon(self, spec_id: int) -> str | None:
        return self._first_asset(
            self.get(
                f"/data/wow/media/playable-specialization/{spec_id}",
                cache_key=f"spec_media_{spec_id}",
            )
        )

    def hero_trees(self, spec_id: int) -> list[dict]:
        """The hero talent trees of a spec, as [{id, name}].

        Names only. The per-tree detail endpoint is advertised in the index but
        answers 404, and a spec's talent tree carries no hero talent nodes, so
        Blizzard exposes no icon for a hero tree and no way to tie one to the talent
        entry IDs Warcraft Logs reports. Both of those stay hand-configured; see
        HeroTree in spells.py.
        """
        spec = self.specialization(spec_id) or {}
        return [
            {"id": t.get("id"), "name": t.get("name")}
            for t in (spec.get("hero_talent_trees") or [])
        ]

    def download(self, url: str, destination: Path) -> bool:
        """Fetch an icon to disk. Skips work when the file is already there."""
        if destination.is_file() and destination.stat().st_size > 0:
            return False
        response = self._http.get(url)
        if response.status_code != 200:
            raise BlizzardError(f"icon download failed ({response.status_code}): {url}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return True

    @staticmethod
    def _first_asset(media: dict | None) -> str | None:
        for asset in (media or {}).get("assets") or []:
            if asset.get("value"):
                return asset["value"]
        return None
