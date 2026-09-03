from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _id_set(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {x.strip() for x in raw.split(",") if x.strip()}


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_base_url: str | None = os.getenv(
        "ANTHROPIC_BASE_URL", "https://opencode.ai/zen/go/v1"
    ) or None
    model: str = os.getenv("MODEL", "deepseek-v4-flash")

    max_steps: int = _int("MAX_STEPS", 12)
    # 超过预算就触发摘要压缩；粗略按 4 字符 ≈ 1 token 估算
    context_token_budget: int = _int("CONTEXT_TOKEN_BUDGET", 24000)

    db_path: Path = Path(os.getenv("DB_PATH", "./data/saiclawbot.db"))

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    allowed_user_ids: set[str] = field(default_factory=lambda: _id_set("ALLOWED_USER_IDS"))


settings = Settings()
