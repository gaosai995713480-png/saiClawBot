"""Agent 执行循环（ReAct 风格）。

一轮 run():
  1. 组装上下文（summary + 历史 + 当前用户消息）
  2. 调 LLM
  3. 若返回 tool_use：校验风险等级 → 并发执行所有工具 → 把 tool_result 写回 → 回到 2
  4. 若返回纯文本或达到 max_steps：结束，返回最终文本

所有 LLM / 工具调用都记 trace。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

import structlog

from ..config import settings
from ..llm import LLM
from ..memory import Memory
from ..storage import Store
from ..tools import Risk, ToolError, ToolRegistry

log = structlog.get_logger()

SYSTEM_PROMPT = """你是 saiClawBot，一个运行在用户个人设备上的 AI 助理。
- 用中文回复，简洁直接。
- 需要事实、文件内容或执行结果时优先调用工具，不要凭空猜测。
- 工具报错时先分析原因再决定重试或换方案，不要无限重复同一调用。
- 完成任务后给出最终回复，不要在回复里复述工具调用过程。
"""

# 危险工具的确认回调：返回 True 表示用户同意执行
ConfirmFn = Callable[[str, dict[str, Any]], Awaitable[bool]]


async def _deny_all(name: str, args: dict[str, Any]) -> bool:
    return False


class AgentRunner:
    def __init__(
        self,
        llm: LLM,
        store: Store,
        memory: Memory,
        tools: ToolRegistry,
        confirm: ConfirmFn = _deny_all,
        max_steps: int = settings.max_steps,
    ) -> None:
        self.llm = llm
        self.store = store
        self.memory = memory
        self.tools = tools
        self.confirm = confirm
        self.max_steps = max_steps

    async def run(self, session_key: str, user_text: str) -> str:
        await self.store.append(session_key, "user", user_text)
        summary, messages = await self.memory.build_context(session_key)
        system = SYSTEM_PROMPT + (f"\n\n[早前对话摘要]\n{summary}" if summary else "")
        tool_schemas = self.tools.to_anthropic()

        for step in range(1, self.max_steps + 1):
            t0 = time.perf_counter()
            resp = await self.llm.chat(system, messages, tool_schemas)
            await self.store.trace(
                session_key, step, "llm",
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                duration_ms=int((time.perf_counter() - t0) * 1000),
            )

            content = [b.model_dump(exclude_none=True) for b in resp.content]
            await self.store.append(session_key, "assistant", content)
            messages.append({"role": "assistant", "content": content})

            tool_uses = [b for b in content if b["type"] == "tool_use"]
            if resp.stop_reason != "tool_use" or not tool_uses:
                return _text_of(content)

            results = await asyncio.gather(
                *(self._exec_tool(session_key, step, tu) for tu in tool_uses)
            )
            await self.store.append(session_key, "user", results)
            messages.append({"role": "user", "content": results})

        # 到达步数上限：强制让模型收尾，不再给工具
        resp = await self.llm.chat(
            system + "\n\n你已用完工具调用次数，请基于现有信息直接给出最终回复。",
            messages, tools=None,
        )
        content = [b.model_dump(exclude_none=True) for b in resp.content]
        await self.store.append(session_key, "assistant", content)
        return _text_of(content)

    async def _exec_tool(self, session_key: str, step: int, tu: dict[str, Any]) -> dict[str, Any]:
        name, args, tid = tu["name"], tu["input"], tu["id"]
        spec = self.tools.get(name)
        t0 = time.perf_counter()
        is_error = False
        try:
            if spec is None:
                raise ToolError(f"unknown tool: {name}")
            if spec.risk >= Risk.DANGER and not await self.confirm(name, args):
                raise ToolError("用户拒绝执行该危险操作")
            out = await self.tools.call(name, args)
        except ToolError as e:
            out, is_error = str(e), True
        except Exception as e:  # 工具内部未预期异常，也回喂给模型而不是让整轮崩掉
            log.exception("tool crashed", tool=name)
            out, is_error = f"tool crashed: {type(e).__name__}: {e}", True

        await self.store.trace(
            session_key, step, "tool", name=name,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            detail=("ERROR " if is_error else "") + out[:500],
        )
        return {"type": "tool_result", "tool_use_id": tid, "content": out, "is_error": is_error}


def _text_of(content: list[dict[str, Any]]) -> str:
    return "".join(b["text"] for b in content if b["type"] == "text").strip()
