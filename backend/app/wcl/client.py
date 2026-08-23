"""Talking to Warcraft Logs v2, or convincingly pretending to.

Three things live here, in the order a request passes through them:

  1. Token. The client-credentials flow: POST the client ID and secret, get a bearer
     token back. Warcraft Logs issues long-lived tokens (about a year), so it is
     cached to disk and only re-fetched on expiry or a 401.
  2. Disk cache. The rate limit is point-based, roughly 3600 points an hour, and a
     fight's event query is the expensive one. Every response is written to
     data/cache keyed by query + variables. A logged fight never changes, so its
     entry is kept for months; rankings expire in hours as new parses land.
  3. Fixture fallback. With no credentials configured, or with RAIDLINE_FORCE_FIXTURES
     set, reads come from app/fixtures instead. That is what lets the app be run and
     demoed with no account at all, and it is the same code path either way: the
     service layer above cannot tell the difference.

Nothing here knows what a spell or a boss is. It moves GraphQL in and JSON out.
"""

import base64
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class WclError(RuntimeError):
    """A Warcraft Logs request failed in a way the caller should surface."""


class FixtureMiss(WclError):
    """Fixture mode was asked for data that was never recorded."""


def _cache_path(kind: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return Path(settings.cache_dir) / kind / f"{digest}.json"


def _cache_read(kind: str, key: str, ttl: int) -> Any | None:
    path = _cache_path(kind, key)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if ttl > 0 and time.time() - payload.get("stored_at", 0) > ttl:
        return None
    return payload.get("data")


def _cache_write(kind: str, key: str, data: Any) -> None:
    path = _cache_path(kind, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"stored_at": time.time(), "key": key, "data": data}
    path.write_text(json.dumps(body), encoding="utf-8")


class TokenStore:
    """Holds the bearer token in memory and on disk.

    On disk as well as in memory because a container restart should not cost a
    round trip, and because a token outlives any single run by roughly a year.
    """

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._path = Path(settings.cache_dir) / "token.json"

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._token = payload.get("access_token")
        self._expires_at = payload.get("expires_at", 0.0)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"access_token": self._token, "expires_at": self._expires_at}),
            encoding="utf-8",
        )

    def invalidate(self) -> None:
        """Drop the token after a 401 so the next call fetches a fresh one."""
        self._token = None
        self._expires_at = 0.0
        self._path.unlink(missing_ok=True)

    async def get(self, http: httpx.AsyncClient) -> str:
        if self._token is None:
            self._load()
        # A minute of slack so a token cannot expire between this check and the call.
        if self._token and time.time() < self._expires_at - 60:
            return self._token

        basic = base64.b64encode(
            f"{settings.wcl_client_id}:{settings.wcl_client_secret}".encode()
        ).decode()
        response = await http.post(
            settings.wcl_token_url,
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {basic}"},
        )
        if response.status_code != 200:
            raise WclError(
                f"token request failed ({response.status_code}). "
                "Check RAIDLINE_WCL_CLIENT_ID / _SECRET, and that the client was "
                "created with Public Client unchecked."
            )
        payload = response.json()
        self._token = payload["access_token"]
        self._expires_at = time.time() + float(payload.get("expires_in", 86400))
        self._save()
        log.info("obtained a new Warcraft Logs token")
        return self._token


_tokens = TokenStore()


async def graphql(
    query: str,
    variables: dict[str, Any],
    *,
    cache_kind: str,
    cache_ttl: int,
) -> dict:
    """Run one query, through the cache, against the API or the fixtures."""
    cache_key = json.dumps(
        {"q": query, "v": variables}, sort_keys=True, separators=(",", ":")
    )

    cached = _cache_read(cache_kind, cache_key, cache_ttl)
    if cached is not None:
        return cached

    if not settings.live_enabled:
        return _fixture(cache_kind, variables)

    async with httpx.AsyncClient(timeout=45.0) as http:
        data = await _post(http, query, variables, retry_on_401=True)

    _cache_write(cache_kind, cache_key, data)
    return data


async def _post(
    http: httpx.AsyncClient,
    query: str,
    variables: dict[str, Any],
    *,
    retry_on_401: bool,
) -> dict:
    token = await _tokens.get(http)
    response = await http.post(
        settings.wcl_api_url,
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {token}"},
    )

    if response.status_code == 401 and retry_on_401:
        # Token rejected: it was revoked or expired early. One retry with a fresh one.
        _tokens.invalidate()
        return await _post(http, query, variables, retry_on_401=False)

    if response.status_code == 429:
        raise WclError(
            "Warcraft Logs rate limit reached (the hourly point budget is spent). "
            "Cached bosses still work; new ones become available when it resets."
        )
    if response.status_code != 200:
        raise WclError(f"Warcraft Logs returned {response.status_code}")

    payload = response.json()
    # GraphQL reports failures in the body with a 200, so this check is not redundant.
    if payload.get("errors"):
        message = "; ".join(e.get("message", "?") for e in payload["errors"])
        raise WclError(f"Warcraft Logs query error: {message}")
    return payload["data"]


def _fixture(kind: str, variables: dict[str, Any]) -> dict:
    """Replay a recorded response.

    Fixtures are named by kind plus the variables that identify them, so a recorded
    boss and a live one are addressed identically. capture.py writes these.
    """
    path = FIXTURES_DIR / f"{fixture_name(kind, variables)}.json"
    if not path.is_file():
        raise FixtureMiss(
            f"no fixture for {path.name}. Raidline is running without Warcraft Logs "
            "credentials, so it can only show what was recorded. Set "
            "RAIDLINE_WCL_CLIENT_ID and RAIDLINE_WCL_CLIENT_SECRET for live data."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_name(kind: str, variables: dict[str, Any]) -> str:
    """The on-disk name of a fixture. Shared with capture.py so recording and
    replaying cannot drift apart."""
    if kind == "rankings":
        return (
            f"rankings_{variables['encounterId']}_{variables['difficulty']}"
            f"_{variables['className']}-{variables['specName']}".lower()
        )
    if kind == "fight":
        return f"fight_{variables['code']}_{variables['fightId']}"
    return kind


async def rate_limit() -> dict:
    """Current point budget. Uncached on purpose: a cached budget is a lie."""
    if not settings.live_enabled:
        return {"live": False}
    from . import queries

    async with httpx.AsyncClient(timeout=20.0) as http:
        data = await _post(http, queries.RATE_LIMIT, {}, retry_on_401=True)
    return {"live": True, **data.get("rateLimitData", {})}
