import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.wechat.db import DatabaseOpenError, detect_tables, open_sqlite, table_columns
from tools.wechat.models import ChatMessage, Contact, ExtractionReport

MESSAGE_TABLE_NAMES = ("MSG", "Msg", "message", "messages")
CONTACT_TABLE_NAMES = ("Contact", "contact", "rcontact")

CONTENT_COLUMNS = ("StrContent", "Content", "content", "message", "msg")
TALKER_COLUMNS = ("StrTalker", "Talker", "talker", "wxid", "username")
SENDER_COLUMNS = ("Sender", "FromUserName", "from_user", "sender", "IsSender")
TIMESTAMP_COLUMNS = ("CreateTime", "createTime", "CreateTimeSvr", "timestamp", "time")
TYPE_COLUMNS = ("Type", "MsgType", "type", "msgType")
LOCAL_ID_COLUMNS = ("LocalId", "localId", "MsgSvrID", "msgId", "id")

TEXT_PLACEHOLDERS = {"[图片]", "[语音]", "[视频]", "[文件]", "[动画表情]", "[表情]", "[表情包]", "[位置]"}
STICKER_RE = re.compile(r"\[(?:表情|动画表情|表情包)(?:[：:][^\]]*)?\]")
QUOTE_RE = re.compile(r"引用\[[^\]]+\]|^\s*>\s*")
XML_PREFIXES = ("<msg", "<appmsg", "<sysmsg", "<?xml")
TEXT_EXPORT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(.+?)\s+\[(.+?)\]\s*(.*)$")
WEFLOW_TEXT_EXPORT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+'(.+?)'\s*$")


def load_messages(
    paths: list[Path],
    wxid: str,
    self_wxid: str | None = None,
    sqlcipher_key: str | None = None,
    limit: int = 5000,
    include_groups: bool = False,
    verbose: bool = False,
) -> tuple[list[ChatMessage], ExtractionReport]:
    all_messages: list[ChatMessage] = []
    report = ExtractionReport()
    for path in paths:
        try:
            conn = open_sqlite(path, sqlcipher_key=sqlcipher_key)
        except DatabaseOpenError as exc:
            report.warnings.append(str(exc))
            continue

        try:
            messages, contacts, warnings = parse_database(
                conn,
                source_name=str(path),
                wxid=wxid,
                self_wxid=self_wxid,
                limit=limit,
                include_groups=include_groups,
                verbose=verbose,
            )
            all_messages.extend(messages)
            report.sources.append(str(path))
            report.warnings.extend(warnings)
        finally:
            conn.close()

    all_messages = _sort_and_limit(all_messages, limit)
    report.total_messages = len(all_messages)
    report.target_messages = sum(1 for msg in all_messages if msg.is_from_target)
    return all_messages, report


def load_export_dir(
    export_dir: Path,
    wxid: str,
    self_wxid: str | None = None,
    limit: int = 5000,
    include_groups: bool = False,
    verbose: bool = False,
) -> tuple[list[ChatMessage], ExtractionReport]:
    db_paths = [path for path in export_dir.rglob("*") if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}]
    json_paths = [path for path in export_dir.rglob("*.json")]
    text_paths = [path for path in export_dir.rglob("*.txt")]
    csv_paths = [path for path in export_dir.rglob("*.csv")]
    messages, report = load_messages(db_paths, wxid, self_wxid, None, limit, include_groups, verbose)

    for path in json_paths:
        parsed = _load_json_messages(path, wxid, self_wxid, include_groups)
        if parsed:
            messages.extend(parsed)
            report.sources.append(str(path))

    for path in text_paths:
        parsed = _load_text_export_messages(path, wxid, self_wxid)
        if parsed:
            messages.extend(parsed)
            report.sources.append(str(path))

    for path in csv_paths:
        parsed = _load_csv_export_messages(path, wxid, self_wxid, include_groups)
        if parsed:
            messages.extend(parsed)
            report.sources.append(str(path))

    messages = _sort_and_limit(messages, limit)
    report.total_messages = len(messages)
    report.target_messages = sum(1 for msg in messages if msg.is_from_target)
    return messages, report


def parse_database(
    conn,
    source_name: str,
    wxid: str,
    self_wxid: str | None = None,
    limit: int = 5000,
    include_groups: bool = False,
    verbose: bool = False,
) -> tuple[list[ChatMessage], dict[str, Contact], list[str]]:
    warnings: list[str] = []
    messages: list[ChatMessage] = []
    contacts = _load_contacts(conn)
    message_tables = find_message_tables(conn)
    if not message_tables:
        warnings.append(f"未在 {source_name} 找到消息表")

    for table in message_tables:
        columns = table_columns(conn, table)
        content_col = _pick(columns, CONTENT_COLUMNS)
        if not content_col:
            warnings.append(f"消息表 {table} 缺少内容列")
            continue

        selected_columns = [content_col]
        for column in [
            _pick(columns, TALKER_COLUMNS),
            _pick(columns, SENDER_COLUMNS),
            _pick(columns, TIMESTAMP_COLUMNS),
            _pick(columns, TYPE_COLUMNS),
            _pick(columns, LOCAL_ID_COLUMNS),
        ]:
            if column and column not in selected_columns:
                selected_columns.append(column)

        query = f"SELECT {', '.join(_quote(column) for column in selected_columns)} FROM {_quote(table)}"
        for row in conn.execute(query):
            row_dict = {column: row[column] for column in selected_columns}
            message = normalize_message_row(row_dict, columns, wxid, self_wxid, source_name, include_groups)
            if message:
                messages.append(message)

    messages = _sort_and_limit(messages, limit)
    return messages, contacts, warnings


def find_message_tables(conn) -> list[str]:
    tables = detect_tables(conn)
    exact = [name for name in MESSAGE_TABLE_NAMES if name in tables]
    fuzzy = [name for name in tables if "msg" in name.lower() or "message" in name.lower()]
    return list(dict.fromkeys(exact + fuzzy))


def find_contact_tables(conn) -> list[str]:
    tables = detect_tables(conn)
    exact = [name for name in CONTACT_TABLE_NAMES if name in tables]
    fuzzy = [name for name in tables if "contact" in name.lower()]
    return list(dict.fromkeys(exact + fuzzy))


def normalize_message_row(
    row: dict[str, Any],
    columns: set[str],
    wxid: str,
    self_wxid: str | None,
    source_name: str,
    include_groups: bool,
) -> ChatMessage | None:
    content = clean_message_text(_get(row, CONTENT_COLUMNS))
    if not content:
        return None

    message_type = _get(row, TYPE_COLUMNS)
    if message_type is not None and str(message_type) not in {"1", "text", "Text"}:
        return None

    talker = str(_get(row, TALKER_COLUMNS) or "")
    sender_value = _get(row, SENDER_COLUMNS)
    sender = str(sender_value) if sender_value is not None else None
    is_sender_flag = _to_int(sender_value) if sender_value is not None else None

    is_group = talker.endswith("@chatroom")
    if is_group and not include_groups:
        return None

    is_related = talker == wxid or sender == wxid or (include_groups and wxid in content)
    if not is_related and not is_group:
        return None

    if sender == wxid:
        is_from_target = True
    elif talker == wxid and is_sender_flag is not None:
        is_from_target = is_sender_flag == 0
    elif talker == wxid and self_wxid and sender == self_wxid:
        is_from_target = False
    elif talker == wxid:
        is_from_target = True
    else:
        is_from_target = False

    return ChatMessage(
        local_id=_get(row, LOCAL_ID_COLUMNS),
        talker=talker,
        sender=sender,
        content=content,
        timestamp=_to_int(_get(row, TIMESTAMP_COLUMNS)),
        is_from_target=is_from_target,
        message_type=message_type,
        source=source_name,
    )


def clean_message_text(content: Any) -> str | None:
    if content is None:
        return None
    text = str(content).strip()
    if not text or text in TEXT_PLACEHOLDERS:
        return None
    if STICKER_RE.fullmatch(text):
        return None
    if QUOTE_RE.match(text):
        return None
    lowered = text.lower()
    if lowered.startswith(XML_PREFIXES):
        return None
    if len(text) < 2:
        return None
    return text


def _load_contacts(conn) -> dict[str, Contact]:
    contacts: dict[str, Contact] = {}
    for table in find_contact_tables(conn):
        columns = table_columns(conn, table)
        wxid_col = _pick(columns, ("UserName", "wxid", "username"))
        if not wxid_col:
            continue
        nickname_col = _pick(columns, ("NickName", "nickname"))
        remark_col = _pick(columns, ("Remark", "remark"))
        alias_col = _pick(columns, ("Alias", "alias"))
        selected = [column for column in [wxid_col, nickname_col, remark_col, alias_col] if column]
        query = f"SELECT {', '.join(_quote(column) for column in selected)} FROM {_quote(table)}"
        for row in conn.execute(query):
            wxid = str(row[wxid_col])
            contacts[wxid] = Contact(
                wxid=wxid,
                nickname=str(row[nickname_col]) if nickname_col and row[nickname_col] else None,
                remark=str(row[remark_col]) if remark_col and row[remark_col] else None,
                alias=str(row[alias_col]) if alias_col and row[alias_col] else None,
            )
    return contacts


def _load_json_messages(path: Path, wxid: str, self_wxid: str | None, include_groups: bool) -> list[ChatMessage]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(data, dict):
        for key in ("messages", "data", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        return []

    messages: list[ChatMessage] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        row = {
            "content": item.get("content") or item.get("message") or item.get("msg") or item.get("StrContent"),
            "talker": item.get("talker") or item.get("wxid") or item.get("StrTalker"),
            "sender": item.get("sender") or item.get("from_user") or item.get("Sender"),
            "timestamp": item.get("timestamp") or item.get("time") or item.get("CreateTime"),
            "type": item.get("type") or item.get("Type") or 1,
            "id": item.get("id") or item.get("LocalId"),
        }
        message = normalize_message_row(row, set(row), wxid, self_wxid, str(path), include_groups)
        if message:
            messages.append(message)
    return messages


def _load_csv_export_messages(path: Path, wxid: str, self_wxid: str | None, include_groups: bool) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    try:
        file = path.open("r", encoding="utf-8-sig", newline="")
    except OSError:
        return []

    with file:
        reader = csv.DictReader(file)
        for index, item in enumerate(reader, 1):
            content = _extract_csv_content(item.get("content") or item.get("Content") or item.get("msg"))
            content = clean_message_text(content)
            if not content:
                continue
            type_name = str(item.get("type_name") or item.get("type") or item.get("Type") or "").lower()
            if type_name and not any(token in type_name for token in ("文字", "text", "1")):
                continue
            talker = str(item.get("talker") or item.get("Talker") or item.get("room_name") or path.stem)
            is_group = talker.endswith("@chatroom") or bool(item.get("room_name"))
            if is_group and not include_groups:
                continue
            if wxid not in {talker, item.get("sender"), item.get("from_user"), path.stem} and wxid != path.stem:
                continue
            is_sender = str(item.get("is_sender") or item.get("IsSender") or "").lower()
            messages.append(ChatMessage(
                local_id=item.get("id") or item.get("MsgSvrID") or index,
                talker=talker,
                sender=item.get("sender") or item.get("from_user"),
                content=content,
                timestamp=parse_export_timestamp(item.get("CreateTime") or item.get("timestamp") or item.get("time")),
                is_from_target=is_sender in {"0", "false", "接收", "receiver", ""},
                message_type=item.get("type_name") or item.get("type"),
                source=str(path),
            ))
    return messages


def _extract_csv_content(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text
        for key in ("msg", "content", "text"):
            if data.get(key):
                return str(data[key])
    return text


def parse_export_timestamp(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            pass
    return None


def _load_text_export_messages(path: Path, wxid: str, self_wxid: str | None) -> list[ChatMessage]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError:
        try:
            lines = path.read_text(encoding="gb18030").splitlines()
        except OSError:
            return []
    except OSError:
        return []

    messages = _load_bracketed_text_export_messages(path, lines, wxid, self_wxid)
    return messages or _load_weflow_text_export_messages(path, lines, wxid, self_wxid)


def _load_bracketed_text_export_messages(path: Path, lines: list[str], wxid: str, self_wxid: str | None) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    target_names = {wxid, path.stem}
    if self_wxid:
        target_names.discard(self_wxid)

    for index, line in enumerate(lines, 1):
        match = TEXT_EXPORT_RE.match(line.strip())
        if not match:
            continue
        time_text, sender, kind, content = match.groups()
        if kind != "文字":
            continue
        content = clean_message_text(content)
        if not content:
            continue
        sender = sender.strip()
        messages.append(ChatMessage(
            local_id=index,
            talker=path.stem,
            sender=sender,
            content=content,
            timestamp=parse_export_timestamp(time_text),
            is_from_target=sender in target_names,
            message_type=1,
            source=str(path),
        ))
    return messages


def _load_weflow_text_export_messages(path: Path, lines: list[str], wxid: str, self_wxid: str | None) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    target_names = {wxid, path.stem, _strip_weflow_prefix(path.stem)}
    if self_wxid:
        target_names.discard(self_wxid)

    index = 0
    local_id = 1
    while index < len(lines):
        match = WEFLOW_TEXT_EXPORT_RE.match(lines[index].strip())
        if not match:
            index += 1
            continue
        time_text, sender = match.groups()
        index += 1
        content_lines: list[str] = []
        while index < len(lines) and not WEFLOW_TEXT_EXPORT_RE.match(lines[index].strip()):
            line = lines[index].strip()
            if line:
                content_lines.append(line)
            index += 1
        content = clean_message_text("\n".join(content_lines))
        if not content:
            continue
        sender = sender.strip()
        messages.append(ChatMessage(
            local_id=local_id,
            talker=_strip_weflow_prefix(path.stem),
            sender=sender,
            content=content,
            timestamp=parse_export_timestamp(time_text),
            is_from_target=sender in target_names,
            message_type=1,
            source=str(path),
        ))
        local_id += 1
    return messages


def _strip_weflow_prefix(value: str) -> str:
    for prefix in ("私聊_", "群聊_"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def _sort_and_limit(messages: list[ChatMessage], limit: int) -> list[ChatMessage]:
    messages.sort(key=lambda message: message.timestamp or 0)
    if limit > 0:
        return messages[-limit:]
    return messages


def _pick(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {column.lower(): column for column in columns}
    for candidate in candidates:
        if candidate in columns:
            return candidate
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def _get(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    lowered = {key.lower(): key for key in row}
    for candidate in candidates:
        if candidate in row:
            return row[candidate]
        if candidate.lower() in lowered:
            return row[lowered[candidate.lower()]]
    return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
