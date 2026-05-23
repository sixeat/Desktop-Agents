from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    local_id: str | int | None
    talker: str
    sender: str | None
    content: str
    timestamp: int | None
    is_from_target: bool
    message_type: int | str | None
    source: str


@dataclass
class Contact:
    wxid: str
    nickname: str | None = None
    remark: str | None = None
    alias: str | None = None


@dataclass
class ExtractionReport:
    total_messages: int = 0
    target_messages: int = 0
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
