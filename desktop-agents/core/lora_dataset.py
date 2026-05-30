import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.explicit_memory import ExplicitMemoryStore
from tools.wechat.models import ChatMessage
from tools.wechat.parsers import clean_message_text

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_+/=-]{32,}")
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
NOISE_PATTERNS = [
    re.compile(r"^\[[^\]]*(其他消息|表情|表情包|图片|语音|视频|文件|位置|转账|红包)[^\]]*\]$"),
    re.compile(r"^【?(淘宝|京东|拼多多|天猫|闲鱼|抖音|小红书|B站|哔哩哔哩)】?"),
    re.compile(r"(点击链接|复制这条信息|打开.*?APP|淘宝搜索|淘口令|￥[A-Za-z0-9]+￥)"),
    re.compile(r"撤回了一条消息"),
    re.compile(r"\[引用 .+?\]"),
]


@dataclass(frozen=True)
class LoraDatasetStats:
    records_seen: int = 0
    examples: int = 0
    skipped_empty: int = 0
    skipped_sensitive: int = 0
    skipped_short: int = 0
    skipped_unpaired: int = 0
    written: int = 0
    warnings: list[str] = field(default_factory=list)

    def with_written(self, written: int) -> "LoraDatasetStats":
        return LoraDatasetStats(
            records_seen=self.records_seen,
            examples=self.examples,
            skipped_empty=self.skipped_empty,
            skipped_sensitive=self.skipped_sensitive,
            skipped_short=self.skipped_short,
            skipped_unpaired=self.skipped_unpaired,
            written=written,
            warnings=list(self.warnings),
        )


@dataclass(frozen=True)
class LoraDatasetResult:
    examples: list[dict[str, Any]]
    stats: LoraDatasetStats


def is_sensitive_text(text: str) -> bool:
    return bool(ExplicitMemoryStore.SENSITIVE_PATTERN.search(text) or TOKEN_PATTERN.search(text))


def is_noise_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in NOISE_PATTERNS)


def sanitize_lora_text(text: str | None, min_chars: int = 2) -> tuple[str | None, str | None]:
    cleaned = clean_message_text(text)
    if not cleaned:
        return None, "empty"
    cleaned = URL_PATTERN.sub("", cleaned).strip()
    if not cleaned:
        return None, "empty"
    if is_noise_text(cleaned):
        return None, "empty"
    if is_sensitive_text(cleaned):
        return None, "sensitive"
    if len(cleaned) < min_chars:
        return None, "short"
    return cleaned, None


def build_lora_dataset(
    messages: list[ChatMessage],
    min_user_chars: int = 2,
    min_assistant_chars: int = 2,
    max_examples: int | None = None,
) -> LoraDatasetResult:
    pending_user: str | None = None
    examples: list[dict[str, Any]] = []
    skipped_empty = 0
    skipped_sensitive = 0
    skipped_short = 0
    skipped_unpaired = 0

    for message in sorted(messages, key=lambda item: item.timestamp or 0):
        min_chars = min_assistant_chars if message.is_from_target else min_user_chars
        text, reason = sanitize_lora_text(message.content, min_chars=min_chars)
        if text is None:
            if reason == "empty":
                skipped_empty += 1
            elif reason == "sensitive":
                skipped_sensitive += 1
            elif reason == "short":
                skipped_short += 1
            if message.is_from_target and pending_user is not None:
                skipped_unpaired += 1
                pending_user = None
            continue

        if message.is_from_target:
            if pending_user is None:
                skipped_unpaired += 1
                continue
            examples.append({"messages": [{"role": "user", "content": pending_user}, {"role": "assistant", "content": text}]})
            pending_user = None
            if max_examples is not None and len(examples) >= max_examples:
                break
        else:
            if pending_user is not None:
                skipped_unpaired += 1
            pending_user = text

    if pending_user is not None:
        skipped_unpaired += 1

    stats = LoraDatasetStats(
        records_seen=len(messages),
        examples=len(examples),
        skipped_empty=skipped_empty,
        skipped_sensitive=skipped_sensitive,
        skipped_short=skipped_short,
        skipped_unpaired=skipped_unpaired,
    )
    return LoraDatasetResult(examples, stats)


def write_lora_jsonl(examples: list[dict[str, Any]], out_path: str | Path, overwrite: bool = False) -> LoraDatasetStats:
    path = Path(out_path)
    if path.exists() and not overwrite:
        raise FileExistsError(f"输出文件已存在：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for example in examples:
            file.write(json.dumps(example, ensure_ascii=False) + "\n")
    return LoraDatasetStats(examples=len(examples), written=len(examples))


def read_lora_jsonl(path: str | Path, limit: int | None = None) -> list[dict[str, Any]]:
    examples = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            examples.append(json.loads(line))
            if limit is not None and len(examples) >= limit:
                break
    return examples


def format_lora_preview(examples: list[dict[str, Any]], user_label: str = "你", assistant_label: str = "目标") -> str:
    blocks = []
    for index, example in enumerate(examples, 1):
        messages = example.get("messages", [])
        user_text = next((message.get("content", "") for message in messages if message.get("role") == "user"), "")
        assistant_text = next((message.get("content", "") for message in messages if message.get("role") == "assistant"), "")
        blocks.append(f"[{index}]\n{user_label}：{user_text}\n{assistant_label}：{assistant_text}")
    return "\n\n".join(blocks)
