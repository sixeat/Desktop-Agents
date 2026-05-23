import csv
import json
import os
import subprocess
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MEMOTRACE_REPO = "https://github.com/LC044/WeChatMsg"
MEMOTRACE_DOWNLOAD_PAGE = "https://memotrace.cn/"

MEMOTRACE_PATHS = [
    os.path.expandvars(r"%LOCALAPPDATA%\WeChatMsg\WeChatMsg.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\WeChatMsg\WeChatMsg.exe"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\WeChatMsg\WeChatMsg.exe"),
    os.path.expanduser(r"~\AppData\Local\WeChatMsg\WeChatMsg.exe"),
    os.path.expanduser(r"~\WeChatMsg\WeChatMsg.exe"),
    os.path.expanduser(r"~\Downloads\WeChatMsg\WeChatMsg.exe"),
    os.path.expanduser(r"~\Downloads\WeChatMsg.exe"),
    os.path.expanduser(r"~\Desktop\WeChatMsg.exe"),
]

MEMOTRACE_EXPORT_PATHS = [
    os.path.expanduser(r"~\Documents\WeChatMsg\export"),
    os.path.expanduser(r"~\WeChatMsg\export"),
    os.path.expanduser(r"~\Documents\export"),
]


@dataclass
class MemoTraceStatus:
    installed: bool
    executable_path: Optional[str] = None
    version: Optional[str] = None
    export_dir: Optional[str] = None
    last_export_time: Optional[float] = None
    recent_exports: List[Dict] = field(default_factory=list)


class MemoTraceIntegration:
    def __init__(self):
        self.status = self._check_installation()

    def _check_installation(self) -> MemoTraceStatus:
        executable = next((path for path in MEMOTRACE_PATHS if os.path.exists(path)), None)
        export_dir = next((path for path in MEMOTRACE_EXPORT_PATHS if os.path.exists(path)), None)
        recent_exports = self.scan_export_dirs([export_dir] if export_dir else MEMOTRACE_EXPORT_PATHS)
        last_export_time = recent_exports[0]["mtime"] if recent_exports else None
        return MemoTraceStatus(
            installed=executable is not None,
            executable_path=executable,
            version=self._detect_version(executable) if executable else None,
            export_dir=export_dir,
            last_export_time=last_export_time,
            recent_exports=recent_exports,
        )

    def _detect_version(self, executable_path: str) -> Optional[str]:
        try:
            version_file = Path(executable_path).parent / "version.txt"
            if version_file.exists():
                return version_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass
        return "unknown"

    def get_setup_guide(self) -> str:
        return (
            "安装 MemoTrace 步骤：\n\n"
            "1. 打开 https://memotrace.cn/ 下载并解压。\n"
            "2. 运行 WeChatMsg.exe / MemoTrace.exe。\n"
            "3. 在 MemoTrace 中选择联系人并导出 JSON/TXT/CSV。\n"
            "4. 回到 Desktop Agents，点击检测导出文件或手动选择文件。\n\n"
            "本项目只读取你主动导出的明文文件，不读取微信进程内存，也不提取密钥。"
        )

    def launch_memotrace(self) -> bool:
        if not self.status.installed or not self.status.executable_path:
            return False
        try:
            subprocess.Popen([self.status.executable_path], cwd=str(Path(self.status.executable_path).parent))
            return True
        except OSError:
            return False

    def open_download_page(self) -> None:
        webbrowser.open(MEMOTRACE_DOWNLOAD_PAGE)

    def scan_export_dirs(self, export_dirs: List[str | None], since_timestamp: Optional[float] = None) -> List[Dict]:
        files: List[Dict] = []
        for export_dir in export_dirs:
            if not export_dir or not os.path.exists(export_dir):
                continue
            for pattern in ("*.json", "*.txt", "*.csv"):
                for path in Path(export_dir).rglob(pattern):
                    try:
                        mtime = path.stat().st_mtime
                        if since_timestamp and mtime <= since_timestamp:
                            continue
                        files.append(self._file_info(path, mtime))
                    except OSError:
                        continue
        files.sort(key=lambda item: item["mtime"], reverse=True)
        return files[:100]

    def scan_for_new_exports(self, since_timestamp: Optional[float] = None) -> List[Dict]:
        return self.scan_export_dirs(MEMOTRACE_EXPORT_PATHS, since_timestamp)

    def wait_for_export(self, timeout: int = 300, poll_interval: int = 5) -> Optional[List[Dict]]:
        started_at = time.time()
        while time.time() - started_at < timeout:
            files = self.scan_for_new_exports(started_at)
            if files:
                return files
            time.sleep(poll_interval)
        return None

    def parse_memotrace_json(self, file_path: str) -> Tuple[str, List[Dict]]:
        data = json.loads(Path(file_path).read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            for key in ("messages", "data", "items"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if not isinstance(data, list):
            return self._contact_name(file_path), []

        messages = []
        for record in data:
            if not isinstance(record, dict):
                continue
            msg_type = record.get("Type", record.get("type", 1))
            if str(msg_type) not in {"1", "text", "Text", "文字"}:
                continue
            content = record.get("StrContent") or record.get("content") or record.get("msg") or record.get("message")
            if not isinstance(content, str):
                continue
            content = content.strip()
            if not content or (content.startswith("<") and content.endswith(">")):
                continue
            messages.append({
                "content": content,
                "is_sender": bool(record.get("IsSender", record.get("is_sender", False))),
                "timestamp": int(record.get("CreateTime", record.get("timestamp", 0)) or 0),
                "msg_type": 1,
            })
        return self._contact_name(file_path), messages

    def parse_memotrace_txt(self, file_path: str) -> Tuple[str, List[Dict]]:
        from tools.wechat.parsers import load_export_dir

        path = Path(file_path)
        contact_name = self._contact_name(file_path)
        parsed, _ = load_export_dir(path.parent, wxid=path.stem)
        messages = [
            {
                "content": message.content,
                "is_sender": not message.is_from_target,
                "timestamp": message.timestamp or 0,
                "msg_type": 1,
            }
            for message in parsed
            if Path(message.source) == path
        ]
        return contact_name, messages

    def parse_memotrace_csv(self, file_path: str) -> Tuple[str, List[Dict]]:
        path = Path(file_path)
        messages = []
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                content = row.get("StrContent") or row.get("content") or row.get("msg") or row.get("message")
                if not content:
                    continue
                messages.append({
                    "content": content.strip(),
                    "is_sender": str(row.get("IsSender") or row.get("is_sender") or "0") in {"1", "true", "True"},
                    "timestamp": self._parse_timestamp(row.get("CreateTime") or row.get("timestamp")),
                    "msg_type": 1,
                })
        return self._contact_name(file_path), messages

    def auto_import(self, file_path: str) -> Optional[Dict]:
        ext = Path(file_path).suffix.lower()
        try:
            if ext == ".json":
                contact_name, messages = self.parse_memotrace_json(file_path)
            elif ext == ".txt":
                contact_name, messages = self.parse_memotrace_txt(file_path)
            elif ext == ".csv":
                contact_name, messages = self.parse_memotrace_csv(file_path)
            else:
                return None
            return {"contact_name": contact_name, "messages": messages, "count": len(messages), "file_path": file_path}
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def get_status_summary(self) -> str:
        status = self.status
        if not status.installed:
            return "MemoTrace 未安装\n可以手动选择已导出的聊天记录文件。"
        lines = ["MemoTrace 已安装", f"路径：{status.executable_path}"]
        if status.export_dir:
            lines.append(f"导出目录：{status.export_dir}")
        if status.recent_exports:
            lines.append(f"最近导出：{len(status.recent_exports)} 个文件")
        return "\n".join(lines)

    def _file_info(self, path: Path, mtime: float) -> Dict:
        return {
            "path": str(path),
            "name": path.name,
            "dir": str(path.parent),
            "size": path.stat().st_size,
            "mtime": mtime,
            "mtime_str": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _contact_name(self, file_path: str) -> str:
        return Path(file_path).stem.split("_")[0]

    def _parse_timestamp(self, value) -> int:
        if value is None or value == "":
            return 0
        text = str(value).strip()
        if text.isdigit():
            return int(text)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                return int(datetime.strptime(text, fmt).timestamp())
            except ValueError:
                pass
        return 0
