import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from config import APP_DB_PATH, CHAT_UI_HISTORY_LIMIT
from core.agent_bus import BusMessage


class ChatStorage:
    def __init__(self, path: str | Path = APP_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def add_message(self, channel: str, message: BusMessage, conversation_title: str | None = None) -> int:
        conversation_id = self._conversation_id(channel, message.anchor_agent_id)
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, channel, anchor_agent_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    updated_at = excluded.updated_at
                """,
                (conversation_id, channel, message.anchor_agent_id, conversation_title, now, now),
            )
            cursor = conn.execute(
                """
                INSERT INTO messages (
                    conversation_id, channel, sender, content, kind, agent_id, anchor_agent_id, timestamp, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    channel,
                    message.sender,
                    message.content,
                    message.kind,
                    message.agent_id,
                    message.anchor_agent_id,
                    message.timestamp,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def load_recent_messages(
        self,
        channel: str,
        anchor_agent_id: str | None = None,
        limit: int = CHAT_UI_HISTORY_LIMIT,
    ) -> list[BusMessage]:
        conversation_id = self._conversation_id(channel, anchor_agent_id)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sender, content, kind, agent_id, anchor_agent_id, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        return [self._message_from_row(row) for row in reversed(rows)]

    def clear_conversation(self, channel: str, anchor_agent_id: str | None = None) -> None:
        conversation_id = self._conversation_id(channel, anchor_agent_id)
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    def _init_schema(self) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    component TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    applied_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL CHECK (channel IN ('direct', 'group')),
                    anchor_agent_id TEXT,
                    title TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    channel TEXT NOT NULL CHECK (channel IN ('direct', 'group')),
                    sender TEXT NOT NULL,
                    content TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    agent_id TEXT,
                    anchor_agent_id TEXT,
                    timestamp REAL NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation_timestamp
                ON messages(conversation_id, timestamp);

                CREATE INDEX IF NOT EXISTS idx_messages_channel_anchor_timestamp
                ON messages(channel, anchor_agent_id, timestamp);
                """
            )
            conn.execute(
                """
                INSERT INTO schema_migrations (component, version, applied_at)
                VALUES ('chat_storage', 1, ?)
                ON CONFLICT(component) DO UPDATE SET version = excluded.version
                """,
                (now,),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _conversation_id(self, channel: str, anchor_agent_id: str | None = None) -> str:
        if channel == "group":
            return "group:main"
        if channel == "direct" and anchor_agent_id:
            return f"direct:{anchor_agent_id}"
        if channel == "direct":
            raise ValueError("direct conversation requires anchor_agent_id")
        raise ValueError(f"unsupported channel: {channel}")

    def _message_from_row(self, row: sqlite3.Row) -> BusMessage:
        return BusMessage(
            sender=str(row["sender"]),
            content=str(row["content"]),
            kind=str(row["kind"]),
            agent_id=row["agent_id"],
            anchor_agent_id=row["anchor_agent_id"],
            timestamp=float(row["timestamp"]),
        )
