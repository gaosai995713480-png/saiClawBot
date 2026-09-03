"""内置工具。import 本模块即完成注册。"""

from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path

from pydantic import BaseModel, Field

from .registry import Risk, ToolError, tool

# 文件类工具只允许在这个目录下活动，防止 LLM 被诱导读写任意路径
WORKSPACE = Path("./data/workspace").resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)


def _safe_path(rel: str) -> Path:
    p = (WORKSPACE / rel).resolve()
    if WORKSPACE not in p.parents and p != WORKSPACE:
        raise ToolError(f"path escapes workspace: {rel}")
    return p


class Empty(BaseModel):
    pass


@tool("get_time", "获取当前本地日期和时间。")
async def get_time(_: Empty) -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S %A")


class ReadFile(BaseModel):
    path: str = Field(description="相对于工作区的文件路径")


@tool("read_file", "读取工作区内的文本文件。")
async def read_file(p: ReadFile) -> str:
    path = _safe_path(p.path)
    if not path.is_file():
        raise ToolError(f"file not found: {p.path}")
    return path.read_text(encoding="utf-8")[:20000]


class WriteFile(BaseModel):
    path: str = Field(description="相对于工作区的文件路径")
    content: str


@tool("write_file", "在工作区内写入文本文件，已存在则覆盖。", risk=Risk.WRITE)
async def write_file(p: WriteFile) -> str:
    path = _safe_path(p.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(p.content, encoding="utf-8")
    return f"wrote {len(p.content)} chars to {p.path}"


class Shell(BaseModel):
    command: str = Field(description="要执行的 shell 命令")
    timeout: int = Field(default=30, ge=1, le=300, description="超时秒数")


@tool("shell", "在工作区目录执行 shell 命令并返回输出。", risk=Risk.DANGER)
async def shell(p: Shell) -> str:
    # DEBT: 目前直接在宿主机执行，后续换成 docker 一次性容器
    proc = await asyncio.create_subprocess_shell(
        p.command,
        cwd=WORKSPACE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=p.timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise ToolError(f"command timed out after {p.timeout}s")
    text = out.decode("utf-8", errors="replace")
    return f"[exit {proc.returncode}]\n{text[-8000:]}"
