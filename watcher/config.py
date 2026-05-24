from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import dotenv_values, load_dotenv

# Smart env loading:
# - An explicit, non-empty shell env var always wins (e.g. a one-off
#   `AI_NEWS_DATABASE_URL=... python -m ...` invocation pointed at Railway).
# - When the shell var is missing or empty, the value from .env is used
#   (covers the original case where the user's shell exports an empty
#   ANTHROPIC_API_KEY that would otherwise mask the real .env value).
load_dotenv(override=False)
_DOTENV_FALLBACK = dotenv_values()

_REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class SmsConfig:
    to_number: str  # may be "" if not configured; checked at send time
    from_number: str  # may be ""
    first_name: str


@dataclass(frozen=True)
class NewsConfig:
    standing_queries: tuple[str, ...]
    lookback_hours: int
    max_candidates: int


@dataclass(frozen=True)
class LlmConfig:
    model: str
    takeover_threshold_notes: str


@dataclass(frozen=True)
class SeedItemSpec:
    category: str
    key: str
    display_name: str
    seed_notes: str


@dataclass(frozen=True)
class Secrets:
    database_url: str
    brave_api_key: str
    anthropic_api_key: str
    twilio_account_sid: str  # may be "" if not configured; checked at send time
    twilio_auth_token: str  # may be ""


@dataclass(frozen=True)
class Config:
    sms: SmsConfig
    news: NewsConfig
    llm: LlmConfig
    seed_items: tuple[SeedItemSpec, ...]
    secrets: Secrets


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name) or _DOTENV_FALLBACK.get(name) or default
    if required and not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val or ""


def load_config(yaml_path: Path | None = None) -> Config:
    yaml_path = yaml_path or (_REPO_ROOT / "config.yaml")
    override_path = _REPO_ROOT / "config.override.yaml"

    raw = _deep_merge(_load_yaml(yaml_path), _load_yaml(override_path))

    sms_raw = raw.get("sms", {})
    sms = SmsConfig(
        to_number=_env("SMS_TO_NUMBER", sms_raw.get("to_number", "")),
        from_number=_env("TWILIO_FROM_NUMBER", sms_raw.get("from_number", "")),
        first_name=sms_raw.get("first_name", "there"),
    )

    news_raw = raw.get("news", {})
    news = NewsConfig(
        standing_queries=tuple(news_raw.get("standing_queries", [])),
        lookback_hours=int(news_raw.get("lookback_hours", 24)),
        max_candidates=int(news_raw.get("max_candidates", 15)),
    )

    llm_raw = raw.get("llm", {})
    llm = LlmConfig(
        model=llm_raw.get("model", "claude-sonnet-4-6"),
        takeover_threshold_notes=llm_raw.get("takeover_threshold_notes", ""),
    )

    seed_items = tuple(
        SeedItemSpec(
            category=item["category"],
            key=item["key"],
            display_name=item["display_name"],
            seed_notes=item.get("seed_notes", ""),
        )
        for item in raw.get("seed_items", [])
    )

    secrets = Secrets(
        database_url=_env("AI_NEWS_DATABASE_URL", required=True),
        brave_api_key=_env("BRAVE_API_KEY", required=True),
        anthropic_api_key=_env("ANTHROPIC_API_KEY", required=True),
        twilio_account_sid=_env("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=_env("TWILIO_AUTH_TOKEN"),
    )

    return Config(sms=sms, news=news, llm=llm, seed_items=seed_items, secrets=secrets)
