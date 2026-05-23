import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from config import PERSONAS_DIR
from core.importer.base import BaseImporter, ChatMessage, ImportResult
from core.importer.personality_analyzer import PersonalityAnalyzer
from tools.wechat.parsers import load_export_dir

from core.importer.wx_mcp_client import WxMCPClient


class WeChatImporter(BaseImporter):
    def __init__(self, output_dir: str | Path | None = None):
        self.mcp = WxMCPClient()
        self.analyzer = PersonalityAnalyzer()
        self.output_dir = Path(output_dir) if output_dir else PERSONAS_DIR

    def status(self) -> Dict:
        status = {"installed": self.mcp.installed(), "ready": False, "needs_install": False, "needs_auth": False}
        if not status["installed"]:
            status["needs_install"] = True
            return status
        status["ready"] = self.mcp.ready()
        if not status["ready"]:
            status["needs_auth"] = True
        return status

    def import_export_path(self, export_path: str | Path, wxid: str, name: str, limit: int = 5000) -> Optional[ImportResult]:
        path = Path(export_path)
        temp_dir = None
        if path.is_dir():
            source_dir = path
        else:
            temp_dir = tempfile.TemporaryDirectory()
            source_dir = Path(temp_dir.name)
            shutil.copy2(path, source_dir / path.name)
        try:
            messages, _ = load_export_dir(source_dir, wxid=wxid, limit=limit)
        finally:
            if temp_dir:
                temp_dir.cleanup()
        converted = [
            ChatMessage(
                sender=message.sender or message.talker,
                content=message.content,
                timestamp=message.timestamp or 0,
                is_from_me=not message.is_from_target,
                msg_type=1,
            )
            for message in messages
        ]
        if not converted:
            return None
        result = self.analyze(converted, name or wxid)
        self._save(result.persona_config)
        return result

    def list_contacts(self) -> List[dict]:
        return self.contacts()

    def contacts(self) -> List[Dict]:
        if not self.mcp.ready():
            return []
        result = []
        for session in self.mcp.contacts(limit=200):
            name = session.get("display_name") or session.get("name") or "未知"
            sid = session.get("id") or session.get("wxid") or session.get("session_id") or ""
            if not sid:
                continue
            result.append({
                "name": name,
                "session_id": sid,
                "wxid": sid,
                "msg_count": session.get("message_count", session.get("msg_count", 0)),
                "type": session.get("type", "private"),
            })
        result.sort(key=lambda item: item["msg_count"], reverse=True)
        return result

    def extract_messages(self, contact_id: str, limit: int = 5000) -> List[ChatMessage]:
        return self.messages(contact_id, limit)

    def messages(self, session: str, limit: int = 5000) -> List[ChatMessage]:
        if not self.mcp.ready():
            return []
        messages = []
        for item in self.mcp.messages(session, limit):
            content = item.get("content", "")
            if not content or not isinstance(content, str):
                continue
            if item.get("type") not in ("text", "", None):
                continue
            content = content.strip()
            if not content or (content.startswith("<") and content.endswith(">")):
                continue
            messages.append(ChatMessage(
                sender=item.get("sender", "未知"),
                content=content,
                timestamp=item.get("time", item.get("timestamp", 0)),
                is_from_me=bool(item.get("is_from_me", False)),
                msg_type=1,
            ))
        return messages

    def analyze_personality(self, messages: List[ChatMessage], contact_name: str = "") -> ImportResult:
        return self.analyzer.analyze(messages, contact_name)

    def analyze(self, messages: List[ChatMessage], name: str = "") -> ImportResult:
        return self.analyze_personality(messages, name)

    def full_import(self, session: str, name: str) -> Optional[ImportResult]:
        messages = self.messages(session, 5000)
        if not messages:
            return None
        result = self.analyze(messages, name)
        self._save(result.persona_config)
        return result

    def _save(self, config: Dict) -> Path:
        name = str(config.get("name") or "unknown")
        safe = "".join(char for char in name if char.isalnum() or char in "_- ").strip().replace(" ", "_") or "unknown"
        path = self.output_dir / f"{safe}.json"
        os.makedirs(path.parent, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
        return path
