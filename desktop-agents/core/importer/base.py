from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class ChatMessage:
    sender: str
    content: str
    timestamp: int
    is_from_me: bool
    msg_type: int = 1


@dataclass
class ImportResult:
    contact_name: str
    total_messages: int
    text_messages: int
    persona_config: dict
    top_phrases: List[tuple]
    top_emojis: List[tuple]
    avg_reply_length: float
    question_ratio: float


class BaseImporter(ABC):
    @abstractmethod
    def list_contacts(self) -> List[dict]:
        pass

    @abstractmethod
    def extract_messages(self, contact_id: str, limit: int = 5000) -> List[ChatMessage]:
        pass

    @abstractmethod
    def analyze_personality(self, messages: List[ChatMessage]) -> ImportResult:
        pass
