"""入口：python -m saiclawbot [cli|telegram]"""

from __future__ import annotations

import asyncio
import sys

import structlog

from .agent import AgentRunner
from .config import settings
from .gateway.message import InboundMessage
from .llm import LLM
from .memory import Memory
from .storage import Store
from .tools import registry

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="%H:%M:%S"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger()


async def main(channel_name: str) -> None:
    if not settings.anthropic_api_key:
        sys.exit("ANTHROPIC_API_KEY 未配置，请复制 .env.example 为 .env 并填写")

    store = Store(settings.db_path)
    await store.open()
    llm = LLM()
    memory = Memory(store, llm, settings.context_token_budget)

    if channel_name == "cli":
        from .gateway.cli import CliChannel
        channel = CliChannel()
        confirm = channel.confirm
    elif channel_name == "telegram":
        from .gateway.telegram import from_settings
        channel = from_settings()
        confirm = None
    else:
        sys.exit(f"unknown channel: {channel_name}")

    runner = AgentRunner(llm, store, memory, registry, **({"confirm": confirm} if confirm else {}))
    log.info("boot", model=settings.model, tools=[t.name for t in registry.specs()], channel=channel_name)

    async def handle(msg: InboundMessage) -> str:
        if msg.text == "/reset":
            await store.clear(msg.session_key)
            return "会话已清空。"
        try:
            return await runner.run(msg.session_key, msg.text)
        except Exception as e:
            log.exception("agent run failed", session=msg.session_key)
            return f"出错了：{type(e).__name__}: {e}"

    try:
        await channel.run(handle)
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "cli"))
