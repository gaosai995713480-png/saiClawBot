"""SQLite 持久化：会话消息、长期记忆摘要、调用 trace。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,        -- JSON: Anthropic message content blocks
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_key, id);

CREATE TABLE IF NOT EXISTS summaries (
    session_key TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    upto_message_id INTEGER NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT NOT NULL,
    step INTEGER NOT NULL,
    kind TEXT NOT NULL,           -- llm | tool
    name TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    duration_ms INTEGER,
    detail TEXT,
    created_at REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Store not opened"
        return self._db

    # ---- messages ----
    async def append(self, session_key: str, role: str, content: Any) -> int:
        cur = await self.db.execute(
            "INSERT INTO messages(session_key, role, content, created_at) VALUES (?,?,?,?)",
            (session_key, role, json.dumps(content, ensure_ascii=False), time.time()),
        )
        await self.db.commit()
        return cur.lastrowid  # type: ignore[return-value]

    async def history(self, session_key: str, after_id: int = 0) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            "SELECT id, role, content FROM messages WHERE session_key=? AND id>? ORDER BY id",
            (session_key, after_id),
        )
        rows = await cur.fetchall()
        return [{"id": r["id"], "role": r["role"], "content": json.loads(r["content"])} for r in rows]

    async def clear(self, session_key: str) -> None:
        await self.db.execute("DELETE FROM messages WHERE session_key=?", (session_key,))
        await self.db.execute("DELETE FROM summaries WHERE session_key=?", (session_key,))
        await self.db.commit()

    # ---- summaries ----
    async def get_summary(self, session_key: str) -> tuple[str, int] | None:
        cur = await self.db.execute(
            "SELECT summary, upto_message_id FROM summaries WHERE session_key=?", (session_key,)
        )
        row = await cur.fetchone()
        return (row["summary"], row["upto_message_id"]) if row else None

    async def set_summary(self, session_key: str, summary: str, upto_message_id: int) -> None:
        await self.db.execute(
            "INSERT INTO summaries(session_key, summary, upto_message_id, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(session_key) DO UPDATE SET summary=excluded.summary, "
            "upto_message_id=excluded.upto_message_id, updated_at=excluded.updated_at",
            (session_key, summary, upto_message_id, time.time()),
        )
        await self.db.commit()

    # ---- traces ----
    async def trace(
        self,
        session_key: str,
        step: int,
        kind: str,
        name: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        duration_ms: int | None = None,
        detail: str | None = None,
    ) -> None:
        await self.db.execute(
            "INSERT INTO traces(session_key, step, kind, name, input_tokens, output_tokens, duration_ms, detail, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (session_key, step, kind, name, input_tokens, output_tokens, duration_ms, detail, time.time()),
        )
        await self.db.commit()
