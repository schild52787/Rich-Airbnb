"""YAML + .env configuration loader."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def _find_project_root() -> Path:
    """Walk up from this file to find the directory containing config.yaml."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "config.yaml").exists():
            return current
        current = current.parent
    # Fallback to cwd
    return Path.cwd()


PROJECT_ROOT = _find_project_root()


def load_env() -> None:
    """Load .env file from project root."""
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)


def load_yaml_config() -> dict[str, Any]:
    """Load config.yaml from project root."""
    config_path = PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"config.yaml not found at {config_path}")
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_env(key: str, default: str | None = None) -> str | None:
    """Get an environment variable."""
    return os.environ.get(key, default)


def get_env_required(key: str) -> str:
    """Get a required environment variable or raise."""
    val = os.environ.get(key)
    if val is None:
        raise RuntimeError(f"Required environment variable {key!r} is not set")
    return val


def get_database_url() -> str:
    """Return the database URL, defaulting to a local SQLite file."""
    default = f"sqlite:///{PROJECT_ROOT / 'proppilot.db'}"
    return get_env("DATABASE_URL", default)


# Load on import
load_env()
settings: dict[str, Any] = load_yaml_config()
