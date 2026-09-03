"""用假 LLM 驱动 AgentRunner，验证循环、工具执行、危险确认、步数上限。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic import BaseModel

from saiclawbot.agent import AgentRunner
from saiclawbot.memory import Memory
from saiclawbot.storage import Store
from saiclawbot.tools import Risk, ToolRegistry, ToolSpec


# ---- fake anthropic response objects ----
@dataclass
class Usage:
    input_tokens: int = 10
    output_tokens: int = 5


@dataclass
class Block:
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict | None = None

    def model_dump(self, exclude_none=True):
        d = {"type": self.type}
        for k in ("text", "id", "name", "input"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        return d


@dataclass
class Resp:
    content: list[Block]
    stop_reason: str
    usage: Usage = field(default_factory=Usage)


def text(s):
    return Resp([Block("text", text=s)], "end_turn")


def tool_use(name, inp, id="t1"):
    return Resp([Block("tool_use", id=id, name=name, input=inp)], "tool_use")


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def chat(self, system, messages, tools=None, max_tokens=4096):
        self.calls.append((system, [m for m in messages], tools))
        if self.script:
            return self.script.pop(0)
        return text("fallback")

    async def summarize(self, transcript):
        return "SUMMARY"


class EchoParams(BaseModel):
    msg: str


async def echo(p: EchoParams) -> str:
    return f"echo:{p.msg}"


@pytest.fixture
async def env(tmp_path: Path):
    store = Store(tmp_path / "t.db")
    await store.open()
    reg = ToolRegistry()
    reg.register(ToolSpec("echo", "echo", EchoParams, echo, Risk.READ))
    reg.register(ToolSpec("danger", "danger", EchoParams, echo, Risk.DANGER))
    yield store, reg
    await store.close()


async def test_plain_reply(env):
    store, reg = env
    llm = FakeLLM([text("hi")])
    r = AgentRunner(llm, store, Memory(store, llm, 10_000), reg)
    assert await r.run("s", "hello") == "hi"
    hist = await store.history("s")
    assert [h["role"] for h in hist] == ["user", "assistant"]


async def test_tool_loop(env):
    store, reg = env
    llm = FakeLLM([tool_use("echo", {"msg": "x"}), text("done")])
    r = AgentRunner(llm, store, Memory(store, llm, 10_000), reg)
    assert await r.run("s", "go") == "done"
    # 第二次 LLM 调用应带上 tool_result
    second_msgs = llm.calls[1][1]
    last = second_msgs[-1]
    assert last["role"] == "user"
    assert last["content"][0]["type"] == "tool_result"
    assert last["content"][0]["content"] == "echo:x"
    assert last["content"][0]["is_error"] is False


async def test_danger_denied_by_default(env):
    store, reg = env
    llm = FakeLLM([tool_use("danger", {"msg": "rm"}), text("ok")])
    r = AgentRunner(llm, store, Memory(store, llm, 10_000), reg)
    await r.run("s", "go")
    result = llm.calls[1][1][-1]["content"][0]
    assert result["is_error"] is True
    assert "拒绝" in result["content"]


async def test_danger_confirmed(env):
    store, reg = env
    llm = FakeLLM([tool_use("danger", {"msg": "rm"}), text("ok")])

    async def yes(name, args):
        return True

    r = AgentRunner(llm, store, Memory(store, llm, 10_000), reg, confirm=yes)
    await r.run("s", "go")
    assert llm.calls[1][1][-1]["content"][0]["content"] == "echo:rm"


async def test_max_steps_forces_finish(env):
    store, reg = env
    llm = FakeLLM([tool_use("echo", {"msg": str(i)}, id=f"t{i}") for i in range(3)] + [text("final")])
    r = AgentRunner(llm, store, Memory(store, llm, 10_000), reg, max_steps=3)
    assert await r.run("s", "loop") == "final"
    # 3 步工具 + 1 次收尾 = 4 次调用，收尾那次不带 tools
    assert len(llm.calls) == 4
    assert llm.calls[-1][2] is None


async def test_memory_compaction(env):
    store, reg = env
    llm = FakeLLM([text("r%d" % i) for i in range(20)])
    r = AgentRunner(llm, store, Memory(store, llm, token_budget=50), reg)
    for i in range(8):
        await r.run("s", "这是一条比较长的用户消息用于撑爆预算 " * 5)
    summary = await store.get_summary("s")
    assert summary is not None and summary[0] == "SUMMARY"
    assert "SUMMARY" in llm.calls[-1][0]  # 摘要进了 system prompt
