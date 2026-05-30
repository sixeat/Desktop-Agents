import json
import re
import sqlite3
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, time as day_time, timedelta
from pathlib import Path
from typing import Any

from config import APP_DB_PATH, MEMORY_RECALL_LOOKBACK_DAYS


@dataclass(frozen=True)
class MemoryCandidate:
    category: str
    summary: str
    source_text: str
    confidence: float = 1.0
    event_time: float | None = None
    remind_after: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryRecord:
    id: int
    category: str
    summary: str
    source_text: str
    confidence: float
    event_time: float | None
    remind_after: float | None
    last_mentioned_at: float | None
    mention_count: int
    status: str
    created_at: float
    updated_at: float
    metadata: dict[str, Any]


class ExplicitMemoryStore:
    EVENT_WORDS = ["考试", "面试", "开会", "会议", "体检", "比赛", "答辩", "旅行", "出差", "上课", "约会", "复诊", "演出"]
    SENSITIVE_PATTERN = re.compile(r"(密码|验证码|token|api\s*key|apikey|密钥|sk-[A-Za-z0-9_-]{12,}|[A-Za-z0-9_-]{28,})", re.IGNORECASE)
    TIME_PATTERN = re.compile(r"大后天|后天|明天|今天|今晚|明早|明晚|下周[一二三四五六日天]?|下星期[一二三四五六日天]?|周[一二三四五六日天]|星期[一二三四五六日天]|\d{4}年\d{1,2}月\d{1,2}[号日]?|\d{1,2}月\d{1,2}[号日]?")

    def __init__(self, path: str | Path = APP_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def extract_candidates(self, text: str, now: datetime | None = None) -> list[MemoryCandidate]:
        text = text.strip()
        if not text or len(text) > 300 or self.SENSITIVE_PATTERN.search(text):
            return []
        now = now or datetime.now()
        candidates: list[MemoryCandidate] = []
        candidates.extend(self._extract_events(text, now))
        candidates.extend(self._extract_preferences(text))
        candidates.extend(self._extract_plans(text, now))
        candidates.extend(self._extract_facts(text))
        return self._dedupe_candidates(candidates)

    def remember_user_message(
        self,
        text: str,
        source_message_id: int | None = None,
        channel: str | None = None,
        anchor_agent_id: str | None = None,
        now: datetime | None = None,
    ) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        for candidate in self.extract_candidates(text, now=now):
            records.append(self._save_candidate(candidate, source_message_id, channel, anchor_agent_id))
        return records

    def relevant_memories(self, user_input: str | None = None, now: datetime | None = None, limit: int = 6) -> list[MemoryRecord]:
        now_ts = (now or datetime.now()).timestamp()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memories
                WHERE status = 'active'
                  AND (remind_after IS NULL OR remind_after > ? OR last_mentioned_at IS NOT NULL)
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (now_ts, limit * 3),
            ).fetchall()
        records = [self._record_from_row(row) for row in rows]
        if not user_input:
            return records[:limit]
        normalized_input = self._normalize_text(user_input)
        matching = [record for record in records if any(token and token in normalized_input for token in self._memory_tokens(record.summary))]
        combined = matching + [record for record in records if record not in matching]
        return combined[:limit]

    def due_memories(self, now: datetime | None = None, limit: int = 1) -> list[MemoryRecord]:
        current = now or datetime.now()
        now_ts = current.timestamp()
        cutoff = (current - timedelta(days=MEMORY_RECALL_LOOKBACK_DAYS)).timestamp()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memories
                WHERE status = 'active'
                  AND category IN ('event', 'plan')
                  AND remind_after IS NOT NULL
                  AND remind_after <= ?
                  AND last_mentioned_at IS NULL
                  AND mention_count = 0
                  AND (event_time IS NULL OR event_time >= ?)
                ORDER BY remind_after ASC, id ASC
                LIMIT ?
                """,
                (now_ts, cutoff, limit),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def mark_mentioned(self, memory_id: int, now: datetime | None = None) -> None:
        now_ts = (now or datetime.now()).timestamp()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE memories
                SET last_mentioned_at = ?, mention_count = mention_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (now_ts, now_ts, memory_id),
            )

    def format_for_prompt(self, memories: Sequence[MemoryRecord]) -> str:
        lines = [f"- {self._category_label(memory.category)}：{memory.summary}" for memory in memories]
        return "\n".join(lines)

    def compose_followup(self, memory: MemoryRecord, now: datetime | None = None) -> str:
        current = now or datetime.now()
        if memory.event_time:
            event_date = datetime.fromtimestamp(memory.event_time).date()
            days = (current.date() - event_date).days
        else:
            days = 0
        if "考试" in memory.summary and days == 1:
            return "你昨天说要考试，考得怎么样？"
        if days == 1:
            return f"你昨天说要{memory.summary}，怎么样了？"
        if days == 2:
            return f"你前两天说要{memory.summary}，后来还顺利吗？"
        return f"你之前说要{memory.summary}，后来还顺利吗？"

    def _extract_events(self, text: str, now: datetime) -> list[MemoryCandidate]:
        if not re.search(r"我|俺|本人|咱", text):
            return []
        time_match = self.TIME_PATTERN.search(text)
        event_word = next((word for word in self.EVENT_WORDS if word in text), None)
        if not time_match or not event_word:
            return []
        event_dt = self._parse_time_text(time_match.group(0), now)
        if event_dt is None:
            return []
        remind_dt = datetime.combine(event_dt.date() + timedelta(days=1), day_time(hour=8))
        return [MemoryCandidate(
            category="event",
            summary=event_word,
            source_text=text,
            event_time=event_dt.timestamp(),
            remind_after=remind_dt.timestamp(),
            metadata={"time_text": time_match.group(0)},
        )]

    def _extract_preferences(self, text: str) -> list[MemoryCandidate]:
        patterns = [
            (r"我(?:很|特别|比较|更)?喜欢(.+)", "喜欢{value}"),
            (r"我不喜欢(.+)", "不喜欢{value}"),
            (r"我讨厌(.+)", "讨厌{value}"),
            (r"我偏好(.+)", "偏好{value}"),
            (r"我更希望(.+)", "更希望{value}"),
        ]
        return self._extract_simple_patterns(text, "preference", patterns)

    def _extract_plans(self, text: str, now: datetime) -> list[MemoryCandidate]:
        match = re.search(r"我(?:打算|准备|计划|想|想要|准备要)(.+)", text)
        if not match:
            return []
        summary = self._clean_summary(match.group(1))
        if not summary:
            return []
        time_match = self.TIME_PATTERN.search(text)
        event_dt = self._parse_time_text(time_match.group(0), now) if time_match else None
        remind_after = None
        metadata: dict[str, Any] = {}
        if event_dt is not None:
            remind_after = datetime.combine(event_dt.date() + timedelta(days=1), day_time(hour=8)).timestamp()
            metadata["time_text"] = time_match.group(0)
        return [MemoryCandidate("plan", summary, text, event_time=event_dt.timestamp() if event_dt else None, remind_after=remind_after, metadata=metadata)]

    def _extract_facts(self, text: str) -> list[MemoryCandidate]:
        patterns = [
            (r"我叫([\w一-鿿]{1,20})", "名字是{value}"),
            (r"我的生日是(.+)", "生日是{value}"),
            (r"我是(.+)", "身份是{value}"),
            (r"我在(.+?)(?:工作|上学|学习|生活|住)", "在{value}"),
        ]
        return self._extract_simple_patterns(text, "fact", patterns)

    def _extract_simple_patterns(self, text: str, category: str, patterns: list[tuple[str, str]]) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        for pattern, template in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            value = self._clean_summary(match.group(1))
            if value:
                candidates.append(MemoryCandidate(category, template.format(value=value), text))
        return candidates

    def _parse_time_text(self, value: str, now: datetime) -> datetime | None:
        if value in {"今天", "今晚"}:
            return datetime.combine(now.date(), day_time(hour=20 if value == "今晚" else 12))
        if value in {"明天", "明早", "明晚"}:
            hour = 8 if value == "明早" else 20 if value == "明晚" else 12
            return datetime.combine(now.date() + timedelta(days=1), day_time(hour=hour))
        if value == "后天":
            return datetime.combine(now.date() + timedelta(days=2), day_time(hour=12))
        if value == "大后天":
            return datetime.combine(now.date() + timedelta(days=3), day_time(hour=12))
        weekday_match = re.search(r"(下周|下星期|周|星期)([一二三四五六日天]?)", value)
        if weekday_match:
            day = weekday_match.group(2)
            if not day:
                return datetime.combine(now.date() + timedelta(days=7), day_time(hour=12))
            target = "一二三四五六日天".index(day)
            if target == 7:
                target = 6
            current = now.weekday()
            delta = (target - current) % 7
            if weekday_match.group(1) in {"下周", "下星期"}:
                delta += 7 if delta == 0 else 0
            elif delta == 0:
                delta = 7
            return datetime.combine(now.date() + timedelta(days=delta), day_time(hour=12))
        full_match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})[号日]?", value)
        if full_match:
            return datetime(int(full_match.group(1)), int(full_match.group(2)), int(full_match.group(3)), 12)
        month_match = re.fullmatch(r"(\d{1,2})月(\d{1,2})[号日]?", value)
        if month_match:
            year = now.year
            dt = datetime(year, int(month_match.group(1)), int(month_match.group(2)), 12)
            if dt.date() < now.date():
                dt = datetime(year + 1, int(month_match.group(1)), int(month_match.group(2)), 12)
            return dt
        return None

    def _save_candidate(
        self,
        candidate: MemoryCandidate,
        source_message_id: int | None,
        channel: str | None,
        anchor_agent_id: str | None,
    ) -> MemoryRecord:
        now = time.time()
        dedupe_key = self._dedupe_key(candidate)
        metadata_json = json.dumps(candidate.metadata, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    category, summary, source_text, source_message_id, channel, anchor_agent_id,
                    confidence, event_time, remind_after, status, dedupe_key, metadata_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    source_text = excluded.source_text,
                    source_message_id = excluded.source_message_id,
                    channel = excluded.channel,
                    anchor_agent_id = excluded.anchor_agent_id,
                    confidence = MAX(memories.confidence, excluded.confidence),
                    updated_at = excluded.updated_at
                """,
                (
                    candidate.category,
                    candidate.summary,
                    candidate.source_text,
                    source_message_id,
                    channel,
                    anchor_agent_id,
                    candidate.confidence,
                    candidate.event_time,
                    candidate.remind_after,
                    dedupe_key,
                    metadata_json,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM memories WHERE dedupe_key = ?", (dedupe_key,)).fetchone()
        return self._record_from_row(row)

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

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    source_message_id INTEGER,
                    channel TEXT,
                    anchor_agent_id TEXT,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    event_time REAL,
                    remind_after REAL,
                    last_mentioned_at REAL,
                    mention_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    dedupe_key TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_dedupe_key
                ON memories(dedupe_key);

                CREATE INDEX IF NOT EXISTS idx_memories_category_status_time
                ON memories(category, status, event_time);

                CREATE INDEX IF NOT EXISTS idx_memories_remind_after
                ON memories(status, remind_after, last_mentioned_at);
                """
            )
            conn.execute(
                """
                INSERT INTO schema_migrations (component, version, applied_at)
                VALUES ('explicit_memory', 1, ?)
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

    def _record_from_row(self, row: sqlite3.Row) -> MemoryRecord:
        metadata = json.loads(row["metadata_json"] or "{}")
        return MemoryRecord(
            id=int(row["id"]),
            category=str(row["category"]),
            summary=str(row["summary"]),
            source_text=str(row["source_text"]),
            confidence=float(row["confidence"]),
            event_time=row["event_time"],
            remind_after=row["remind_after"],
            last_mentioned_at=row["last_mentioned_at"],
            mention_count=int(row["mention_count"]),
            status=str(row["status"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            metadata=metadata,
        )

    def _dedupe_candidates(self, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        seen: set[str] = set()
        result: list[MemoryCandidate] = []
        for candidate in candidates:
            key = self._dedupe_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            result.append(candidate)
        return result

    def _dedupe_key(self, candidate: MemoryCandidate) -> str:
        date_key = ""
        if candidate.event_time:
            date_key = datetime.fromtimestamp(candidate.event_time).date().isoformat()
        return f"{candidate.category}:{self._normalize_text(candidate.summary)}:{date_key}"

    def _memory_tokens(self, summary: str) -> list[str]:
        normalized = self._normalize_text(summary)
        return [token for token in re.split(r"\s+", normalized) if token] + [normalized]

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

    def _clean_summary(self, text: str) -> str:
        return re.sub(r"[。！？!?,，、；;\s]+$", "", text.strip())[:60]

    def _category_label(self, category: str) -> str:
        return {
            "event": "事件",
            "preference": "偏好",
            "plan": "计划",
            "fact": "事实",
        }.get(category, category)
