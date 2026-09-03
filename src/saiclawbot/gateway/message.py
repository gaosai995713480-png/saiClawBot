"""统一的内部消息模型。所有渠道适配器都把平台消息归一成 InboundMessage，
Agent 只认这个模型，不感知渠道差异。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InboundMessage:
    channel: str  # "cli" | "telegram" | "feishu" ...
    user_id: str  # 渠道内用户唯一标识
    chat_id: str  # 渠道内会话标识（私聊=用户，群聊=群）
    text: str

    @property
    def session_key(self) -> str:
        return f"{self.channel}:{self.chat_id}"
