"""Central configuration loader.

Loads the curated series configuration and resolves project paths and
environment-driven settings. Nothing secret is stored here - database and
optional AI credentials are read from environment variables at call time so
they never need to be committed to the repository.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

# Project root = two levels up from this file (python/common/config.py -> repo root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = DATA_DIR / "reference"
DOCS_DIR = PROJECT_ROOT / "documentation"

SERIES_CONFIG_PATH = CONFIG_DIR / "series_config.json"


@lru_cache(maxsize=1)
def load_series_config() -> dict[str, Any]:
    """Load and cache the series configuration JSON."""
    if not SERIES_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Series configuration not found at {SERIES_CONFIG_PATH}. "
            "The repository ships this file; check your working directory."
        )
    with SERIES_CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_data_dirs() -> None:
    """Create the raw / processed / reference data directories if missing."""
    for directory in (RAW_DIR, PROCESSED_DIR, REFERENCE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class DatabaseConfig:
    """PostgreSQL connection settings, sourced entirely from the environment.

    No defaults contain real credentials. If the environment is not
    configured the loader still succeeds so that the CSV-only pipeline can
    run; only the PostgreSQL loading step requires these values.
    """

    host: str
    port: str
    database: str
    user: str
    password: str

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.database and self.user)

    @property
    def sqlalchemy_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


def load_database_config() -> DatabaseConfig:
    """Read PostgreSQL settings from environment variables (never hard-coded)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    return DatabaseConfig(
        host=os.getenv("PGHOST", ""),
        port=os.getenv("PGPORT", "5432"),
        database=os.getenv("PGDATABASE", ""),
        user=os.getenv("PGUSER", ""),
        password=os.getenv("PGPASSWORD", ""),
    )


def get_setting(key: str, default: Any = None) -> Any:
    """Fetch an ingestion setting from the config file."""
    return load_series_config().get("ingestion_settings", {}).get(key, default)
