"""Configuration loaded from the environment.

The API key is read from `.env` (gitignored) and never written to disk, logs,
or any committed file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Regional routing values accepted by Account-V1 and Match-V5.
VALID_ROUTING = {"americas", "europe", "asia", "sea"}


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


@dataclass(frozen=True)
class Settings:
    api_key: str
    region: str
    routing: str
    riot_id: str | None
    duckdb_path: Path
    raw_data_dir: Path

    @property
    def platform_host(self) -> str:
        """Host for platform-routed endpoints (Summoner-V4, Champion-Mastery-V4)."""
        return f"https://{self.region}.api.riotgames.com"

    @property
    def regional_host(self) -> str:
        """Host for regionally routed endpoints (Account-V1, Match-V5)."""
        return f"https://{self.routing}.api.riotgames.com"


def load_settings(env_file: Path | None = None) -> Settings:
    """Read settings from `.env` plus the process environment."""
    load_dotenv(env_file or PROJECT_ROOT / ".env")

    api_key = os.getenv("RIOT_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "RIOT_API_KEY is not set. Copy .env.example to .env and add your key "
            "from https://developer.riotgames.com/."
        )
    if api_key.startswith("RGAPI-00000000"):
        raise ConfigError(
            "RIOT_API_KEY is still the placeholder from .env.example. "
            "Add your own key from https://developer.riotgames.com/."
        )

    routing = os.getenv("RIOT_ROUTING", "americas").strip().lower()
    if routing not in VALID_ROUTING:
        raise ConfigError(
            f"RIOT_ROUTING must be one of {sorted(VALID_ROUTING)}, got {routing!r}."
        )

    raw_dir = Path(os.getenv("RAW_DATA_DIR", "data/raw"))
    if not raw_dir.is_absolute():
        raw_dir = PROJECT_ROOT / raw_dir

    duckdb_path = Path(os.getenv("DUCKDB_PATH", "summoner_trends.duckdb"))
    if not duckdb_path.is_absolute():
        duckdb_path = PROJECT_ROOT / duckdb_path

    return Settings(
        api_key=api_key,
        region=os.getenv("RIOT_REGION", "na1").strip().lower(),
        routing=routing,
        riot_id=(os.getenv("RIOT_ID") or "").strip() or None,
        duckdb_path=duckdb_path,
        raw_data_dir=raw_dir,
    )


def split_riot_id(riot_id: str) -> tuple[str, str]:
    """Split "GameName#TAG" into its two parts."""
    if "#" not in riot_id:
        raise ConfigError(
            f"Riot ID {riot_id!r} must be in gameName#tagLine form, e.g. Faker#KR1."
        )
    game_name, _, tag_line = riot_id.partition("#")
    game_name, tag_line = game_name.strip(), tag_line.strip()
    if not game_name or not tag_line:
        raise ConfigError(f"Riot ID {riot_id!r} is missing a game name or tag line.")
    return game_name, tag_line
