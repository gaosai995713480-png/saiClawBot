"""记忆管理：滑窗 + LLM 摘要压缩。

策略：
- 每次组装上下文 = [summary(若有)] + summary 之后的全部原始消息
- 原始消息估算 token 超过预算时，把最旧的一半压进 summary，保留最近一半
- 压缩边界必须落在 user 消息之前，避免把 tool_use / tool_result 对拆开
"""

from __future__ import annotations

import json
from typing import Any

from .llm import LLM
from .storage import Store


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    # 粗估：中英混合大致 4 chars ≈ 1 token；够用来决定何时压缩
    return sum(len(json.dumps(m["content"], ensure_ascii=False)) for m in messages) // 4


def _cut_index(messages: list[dict[str, Any]]) -> int:
    """在中间附近找一个 role=user 且内容是纯文本的位置作为切点。"""
    mid = len(messages) // 2
    for i in range(mid, len(messages)):
        m = messages[i]
        if m["role"] == "user" and isinstance(m["content"], str):
            return i
    return 0


def _render(messages: list[dict[str, Any]]) -> str:
    lines = []
    for m in messages:
        c = m["content"]
        if isinstance(c, str):
            lines.append(f"{m['role']}: {c}")
            continue
        for block in c:
            t = block.get("type")
            if t == "text":
                lines.append(f"{m['role']}: {block['text']}")
            elif t == "tool_use":
                lines.append(f"{m['role']} 调用工具 {block['name']}({json.dumps(block['input'], ensure_ascii=False)})")
            elif t == "tool_result":
                lines.append(f"工具结果: {str(block.get('content'))[:500]}")
    return "\n".join(lines)


class Memory:
    def __init__(self, store: Store, llm: LLM, token_budget: int) -> None:
        self.store = store
        self.llm = llm
        self.budget = token_budget

    async def build_context(self, session_key: str) -> tuple[str | None, list[dict[str, Any]]]:
        """返回 (summary, messages)。必要时先做压缩。"""
        summary = await self.store.get_summary(session_key)
        after_id = summary[1] if summary else 0
        rows = await self.store.history(session_key, after_id=after_id)

        if estimate_tokens(rows) > self.budget and len(rows) > 4:
            cut = _cut_index(rows)
            if cut > 0:
                old, keep = rows[:cut], rows[cut:]
                prev = summary[0] if summary else ""
                transcript = (f"[之前的摘要]\n{prev}\n\n" if prev else "") + _render(old)
                new_summary = await self.llm.summarize(transcript)
                await self.store.set_summary(session_key, new_summary, old[-1]["id"])
                summary = (new_summary, old[-1]["id"])
                rows = keep

        messages = [{"role": r["role"], "content": r["content"]} for r in rows]
        return (summary[0] if summary else None), messages
