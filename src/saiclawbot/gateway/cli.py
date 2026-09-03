"""命令行渠道：本地调试用，不依赖任何平台。"""

from __future__ import annotations

import asyncio
from typing import Any

from . import MessageHandler
from .message import InboundMessage


class CliChannel:
    name = "cli"

    async def confirm(self, tool: str, args: dict[str, Any]) -> bool:
        ans = await asyncio.to_thread(input, f"\n⚠️  即将执行危险工具 {tool} {args}\n允许? [y/N] ")
        return ans.strip().lower() == "y"

    async def run(self, handler: MessageHandler) -> None:
        print("saiClawBot CLI. 输入 /quit 退出，/reset 清空会话。")
        while True:
            try:
                text = await asyncio.to_thread(input, "\n你> ")
            except (EOFError, KeyboardInterrupt):
                break
            text = text.strip()
            if not text:
                continue
            if text == "/quit":
                break
            reply = await handler(InboundMessage(self.name, "local", "local", text))
            print(f"\nbot> {reply}")
