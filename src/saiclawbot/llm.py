"""LLM 客户端薄封装。只做一件事：把 messages + tools 发给模型，返回原始响应。
不在这里做任何编排逻辑，编排在 agent/runner.py。"""

from __future__ import annotations

from typing import Any

from anthropic import AsyncAnthropic

from .config import settings


def _sdk_base_url(base_url: str | None) -> str | None:
    """Anthropic SDK 自行附加 /v1/messages，兼容供应商文档中的 /v1 根地址。"""
    if not base_url:
        return None
    normalized = base_url.rstrip("/")
    return normalized.removesuffix("/v1")


class LLM:
    def __init__(self) -> None:
        self.client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            base_url=_sdk_base_url(settings.anthropic_base_url),
        )
        self.model = settings.model

    async def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ):
        kwargs: dict[str, Any] = dict(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
        return await self.client.messages.create(**kwargs)

    async def summarize(self, transcript: str) -> str:
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=(
                "你是对话压缩器。把下面的对话压缩成一段简洁的中文摘要，"
                "保留：用户身份/偏好、已确认的事实、未完成的任务、重要的工具执行结果。"
                "丢弃寒暄和已完成且无后续影响的细节。"
            ),
            messages=[{"role": "user", "content": transcript}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")
