"""Telegram 渠道。需要 `pip install -e .[telegram]`。

安全：只响应 ALLOWED_USER_IDS 白名单内的用户；危险工具默认拒绝
（DEBT: 后续用 inline keyboard 做二次确认）。
"""

from __future__ import annotations

import structlog
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler as TgMessageHandler, filters

from ..config import settings
from . import MessageHandler
from .message import InboundMessage

log = structlog.get_logger()


class TelegramChannel:
    name = "telegram"

    def __init__(self, token: str, allowed: set[str]) -> None:
        self.token = token
        self.allowed = allowed

    async def run(self, handler: MessageHandler) -> None:
        app = Application.builder().token(self.token).build()

        async def on_text(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.message or not update.message.text or not update.effective_user:
                return
            uid = str(update.effective_user.id)
            if uid not in self.allowed:
                log.warning("rejected user", user_id=uid)
                return
            msg = InboundMessage(self.name, uid, str(update.effective_chat.id), update.message.text)
            reply = await handler(msg)
            await update.message.reply_text(reply or "(空回复)")

        app.add_handler(TgMessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

        async with app:
            await app.start()
            await app.updater.start_polling()  # type: ignore[union-attr]
            log.info("telegram polling started")
            try:
                import asyncio
                await asyncio.Event().wait()
            finally:
                await app.updater.stop()  # type: ignore[union-attr]
                await app.stop()


def from_settings() -> TelegramChannel:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    return TelegramChannel(settings.telegram_bot_token, settings.allowed_user_ids)
