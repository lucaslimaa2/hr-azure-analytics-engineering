"""Configuration loaded from the environment.

In Azure these arrive as Function App application settings (secrets via Key Vault
references); locally from ``local.settings.json`` / ``.env``. Nothing secret is
hardcoded or committed. Since the source is generated in-pipeline, there's **no
external API key** — only storage settings and generation parameters.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

from .generate import GenConfig


class ConfigError(RuntimeError):
    """Raised when a required setting is missing."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(
            f"required setting {name!r} is not set "
            "(Function App application setting / Key Vault reference, "
            "or local.settings.json / .env for local runs)"
        )
    return value


@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration. Python only writes raw, so all it needs is
    the lake URL (the SQL transform handles curated itself)."""

    storage_account_url: str  # e.g. https://hrdatalake.dfs.core.windows.net

    @classmethod
    def from_env(cls) -> Config:
        return cls(storage_account_url=_require("STORAGE_ACCOUNT_URL"))


def gen_config_from_env() -> GenConfig:
    """Build the generator config from env, falling back to GenConfig defaults."""
    d = GenConfig()
    start = os.environ.get("GEN_START_DATE")
    return GenConfig(
        start_date=date.fromisoformat(start) if start else d.start_date,
        seed=int(os.environ.get("GEN_SEED", d.seed)),
        start_count=int(os.environ.get("GEN_START_COUNT", d.start_count)),
        hires_per_month=int(os.environ.get("GEN_HIRES_PER_MONTH", d.hires_per_month)),
        term_rate=float(os.environ.get("GEN_TERM_RATE", d.term_rate)),
    )
