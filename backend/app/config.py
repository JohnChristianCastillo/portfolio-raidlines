"""Raidline service configuration.

Overridable via environment variables (prefix RAIDLINE_) or a .env file. Raidline
reads public Warcraft Logs ranking data and renders the top parses' cooldown usage
as a comparable timeline, then exports it as a Method Raid Tools reminder string.

The Warcraft Logs credentials are read from the environment and never committed.
With them absent the app still runs: it serves the recorded fixtures in
app/fixtures instead, which is what makes the whole thing testable offline.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAIDLINE_", env_file=".env", extra="ignore"
    )

    app_name: str = "raidline"
    host: str = "0.0.0.0"
    port: int = 8600

    # Directory of the built frontend to serve (production). Empty in dev (Vite serves
    # the SPA). The Docker image sets this to the copied build output.
    static_dir: str = ""

    # Browser origins allowed to call the API directly (Vite dev server).
    cors_origins_csv: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Warcraft Logs API v2 (see _local/wcl_api_registration/how_to_setup.md) -----
    # Self-registered at warcraftlogs.com/api/clients/, free. Both values are required
    # together; either one missing means live mode is off and fixtures are served.
    wcl_client_id: str = ""
    wcl_client_secret: str = ""
    wcl_token_url: str = "https://www.warcraftlogs.com/oauth/token"
    # The public-data endpoint. The /api/v2/user endpoint needs the authorization-code
    # flow and only exposes the signed-in user's own reports, which Raidline never reads.
    wcl_api_url: str = "https://www.warcraftlogs.com/api/v2/client"

    # Serve fixtures even when credentials exist. Useful for working on the UI without
    # spending the hourly point budget.
    force_fixtures: bool = False

    # --- caching --------------------------------------------------------------------
    # The rate limit is point-based (3600/hour by default) and event queries are by far
    # the most expensive call, so every WCL response is cached to disk and re-read from
    # there. Rankings churn as new parses land; a fight's events never change once
    # logged, so they are cached effectively forever.
    cache_dir: str = "data/cache"
    rankings_ttl_seconds: int = 6 * 3600
    events_ttl_seconds: int = 90 * 24 * 3600
    catalog_ttl_seconds: int = 24 * 3600

    # How many parses to pull per boss/difficulty. The spec fixes this at the top 10.
    top_n: int = 10

    # --- Blizzard Game Data API (develop.battle.net) --------------------------------
    # Build-time only: spell names, descriptions and icons, plus specialisation icons.
    # Everything is baked into the static output, so serving never calls Blizzard.
    blizzard_client_id: str = ""
    blizzard_client_secret: str = ""
    blizzard_token_url: str = "https://oauth.battle.net/token"
    blizzard_host: str = "https://eu.api.blizzard.com"
    # static-<region> resolves to the current game build. Pinning a build namespace
    # works too but goes stale on every patch.
    blizzard_namespace: str = "static-eu"
    blizzard_locale: str = "en_GB"

    # Show only the current expansion's raids. Warcraft Logs lists every tier back to
    # Classic, which buries the one people are actually progressing. Set to 0 to get
    # the full history back in the dropdown.
    current_expansion_only: bool = True

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_csv.split(",") if o.strip()]

    @property
    def blizzard_enabled(self) -> bool:
        return bool(self.blizzard_client_id and self.blizzard_client_secret)

    @property
    def live_enabled(self) -> bool:
        """True when we can talk to Warcraft Logs rather than replay fixtures."""
        return bool(
            self.wcl_client_id and self.wcl_client_secret and not self.force_fixtures
        )


settings = Settings()
