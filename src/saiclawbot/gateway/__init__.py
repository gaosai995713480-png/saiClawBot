from __future__ import annotations

from typing import Protocol, runtime_checkable

from .message import InboundMessage


@runtime_checkable
class Channel(Protocol):
    """渠道适配器协议：把平台事件转成 InboundMessage 交给 handler，
    并把 handler 的回复送回平台。新增渠道只需实现这个协议。"""

    name: str

    async def run(self, handler: "MessageHandler") -> None: ...


class MessageHandler(Protocol):
    async def __call__(self, msg: InboundMessage) -> str: ...
