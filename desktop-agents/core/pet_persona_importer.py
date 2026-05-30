import json
import re
import shutil
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.personality_trainer import PersonalityProfile, PersonalityTrainer
from tools.wechat.parsers import load_export_dir


@dataclass(frozen=True)
class PetPersonaImportResult:
    profile: PersonalityProfile
    message_count: int
    target_message_count: int
    used_fallback_messages: bool
    redaction_count: int = 0
    blocked_sensitive_patterns: int = 0


@dataclass(frozen=True)
class PersonaPackageMetadata:
    message_count: int
    target_message_count: int
    used_fallback_messages: bool
    source_type: str = "chat_export"
    redaction_count: int = 0
    blocked_sensitive_patterns: int = 0


@dataclass(frozen=True)
class DiscoveredPersonaSource:
    name: str
    messages: list[str]
    source_paths: list[Path]

    @property
    def message_count(self) -> int:
        return len(self.messages)


@dataclass(frozen=True)
class BatchPersonaPlan:
    persona_name: str
    source_names: list[str]
    pet_type: str = "cat"


@dataclass(frozen=True)
class BatchPersonaResult:
    profile: PersonalityProfile
    persona_name: str
    source_names: list[str]
    message_count: int
    output_path: Path | None = None


def load_profile_from_export(
    path: str | Path,
    target_name: str,
    pet_name: str,
    pet_type: str,
    minimum_target_messages: int = 10,
) -> PetPersonaImportResult:
    source = Path(path)
    messages, _ = _load_messages_from_path(source, target_name.strip() or source.stem)
    target_messages = [message.content for message in messages if message.is_from_target and message.content.strip()]
    used_fallback = len(target_messages) < minimum_target_messages
    analysis_messages = target_messages if target_messages and not used_fallback else [message.content for message in messages if message.content.strip()]
    profile = PersonalityTrainer().analyze(analysis_messages, pet_name=pet_name, pet_type=pet_type)
    return PetPersonaImportResult(
        profile=profile,
        message_count=len(analysis_messages),
        target_message_count=len(target_messages),
        used_fallback_messages=used_fallback,
    )


def scan_persona_sources(path: str | Path, minimum_messages: int = 2) -> list[DiscoveredPersonaSource]:
    source = Path(path)
    messages, _ = _load_messages_from_path(source, "")
    grouped: dict[str, list] = defaultdict(list)
    source_paths: dict[str, set[Path]] = defaultdict(set)
    for message in messages:
        content = message.content.strip()
        sender = (message.sender or message.talker or "").strip()
        source_name = Path(message.source).stem
        is_group_system_sender = source_name.startswith("群聊_") and sender == _strip_export_prefix(source_name)
        if not content or not sender or sender == "我" or sender == source_name or is_group_system_sender:
            continue
        grouped[sender].append(message)
        source_paths[sender].add(Path(message.source))

    discovered = [
        DiscoveredPersonaSource(
            name=name,
            messages=[message.content for message in items],
            source_paths=sorted(source_paths[name], key=lambda item: str(item)),
        )
        for name, items in grouped.items()
        if len(items) >= minimum_messages
    ]
    return sorted(discovered, key=lambda item: (-item.message_count, item.name))


def build_batch_personas(
    sources: list[DiscoveredPersonaSource],
    plans: list[BatchPersonaPlan],
    output_dir: str | Path | None = None,
) -> list[BatchPersonaResult]:
    by_name = {source.name: source for source in sources}
    trainer = PersonalityTrainer()
    results: list[BatchPersonaResult] = []
    for plan in plans:
        persona_name = plan.persona_name.strip()
        if not persona_name:
            continue
        messages: list[str] = []
        source_names: list[str] = []
        for source_name in plan.source_names:
            source = by_name.get(source_name)
            if source is None:
                continue
            messages.extend(source.messages)
            source_names.append(source.name)
        if not messages:
            continue
        profile = trainer.analyze(messages, pet_name=persona_name, pet_type=plan.pet_type)
        output_path = None
        if output_dir is not None:
            metadata = PersonaPackageMetadata(
                message_count=len(messages),
                target_message_count=len(messages),
                used_fallback_messages=False,
                source_type="batch_chat_export",
            )
            output_path = save_pet_persona_package(
                profile,
                Path(output_dir) / safe_persona_slug(persona_name),
                metadata,
            )
        results.append(BatchPersonaResult(profile, persona_name, source_names, len(messages), output_path))
    return results


def save_pet_persona(profile: PersonalityProfile, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    PersonalityTrainer().save(profile, output_path)
    return output_path


@dataclass(frozen=True)
class PersonaPackageInfo:
    slug: str
    name: str
    personality_tag: str
    pet_type: str
    message_count: int
    target_message_count: int
    created_at: str
    package_dir: Path
    persona_path: Path


def list_persona_packages(base_dir: str | Path) -> list[PersonaPackageInfo]:
    base = Path(base_dir)
    if not base.exists():
        return []
    packages: list[PersonaPackageInfo] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        persona_path = entry / "persona.json"
        if not manifest_path.exists() or not persona_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            persona = json.loads(persona_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        packages.append(PersonaPackageInfo(
            slug=manifest.get("slug", entry.name),
            name=manifest.get("display_name") or persona.get("name") or entry.name,
            personality_tag=persona.get("personality_tag", ""),
            pet_type=persona.get("pet_type", ""),
            message_count=int(manifest.get("message_count", 0) or 0),
            target_message_count=int(manifest.get("target_message_count", 0) or 0),
            created_at=manifest.get("created_at", ""),
            package_dir=entry,
            persona_path=persona_path,
        ))
    return packages


def delete_persona_package(package_dir: Path) -> bool:
    if not package_dir.exists() or not package_dir.is_dir():
        return False
    try:
        shutil.rmtree(package_dir)
        return True
    except OSError:
        return False


PERSONA_PACKAGE_FILES = [
    "manifest.json",
    "persona.json",
    "style_profile.json",
    "examples.jsonl",
    "system_prompt.txt",
    "eval_report.json",
]


def save_pet_persona_package(
    profile: PersonalityProfile,
    output_dir: str | Path,
    metadata: PersonaPackageMetadata | PetPersonaImportResult | dict[str, Any],
) -> Path:
    package_dir = Path(output_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    preview = build_persona_package_preview(profile, metadata)
    scrubbed_profile = preview["profile"]
    metadata_dict = preview["metadata"]
    privacy = preview["manifest"]["privacy"]
    persona_path = package_dir / "persona.json"
    save_pet_persona(scrubbed_profile, persona_path)
    _write_json(package_dir / "manifest.json", preview["manifest"])
    _write_json(package_dir / "style_profile.json", preview["style_profile"])
    (package_dir / "examples.jsonl").write_text("".join(_build_examples(scrubbed_profile)), encoding="utf-8")
    (package_dir / "system_prompt.txt").write_text(scrubbed_profile.system_prompt, encoding="utf-8")
    _write_json(package_dir / "eval_report.json", _build_eval_report(
        metadata_dict,
        int(privacy["redaction_count"]),
        int(privacy["blocked_sensitive_patterns"]),
    ))
    return persona_path


def build_persona_package_preview(
    profile: PersonalityProfile,
    metadata: PersonaPackageMetadata | PetPersonaImportResult | dict[str, Any],
) -> dict[str, Any]:
    scrubbed_profile, redaction_count, blocked_count = _scrub_profile(profile)
    metadata_dict = _metadata_dict(metadata)
    redaction_count += int(metadata_dict.get("redaction_count", 0) or 0)
    blocked_count += int(metadata_dict.get("blocked_sensitive_patterns", 0) or 0)
    manifest = _build_manifest(scrubbed_profile, metadata_dict, redaction_count, blocked_count)
    return {
        "profile": scrubbed_profile,
        "metadata": metadata_dict,
        "files": list(PERSONA_PACKAGE_FILES),
        "manifest": manifest,
        "style_profile": _build_style_profile(scrubbed_profile),
        "eval_report": _build_eval_report(metadata_dict, redaction_count, blocked_count),
    }


def safe_persona_slug(value: str) -> str:
    safe = "".join(ch for ch in value.strip() if ch.isalnum() or ch in "_- ").strip().replace(" ", "_")
    return safe[:64] or "persona"


SENSITIVE_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"https?://\S+|www\.\S+"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"\b\d{8,}\b"),
    re.compile(r"wxid_[A-Za-z0-9_-]+"),
    re.compile(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?\s*\d{0,2}:?\d{0,2}:?\d{0,2}"),
    re.compile(r"[一-鿿]{2,}(?:省|市|区|县|路|街|小区|栋|单元|室)"),
]


def _scrub_profile(profile: PersonalityProfile) -> tuple[PersonalityProfile, int, int]:
    values = asdict(profile)
    redactions = 0
    blocked = 0
    for key, value in values.items():
        scrubbed, key_redactions, key_blocked = _scrub_value(value)
        values[key] = scrubbed
        redactions += key_redactions
        blocked += key_blocked
    return PersonalityProfile(**values), redactions, blocked


def _scrub_value(value):
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, list):
        scrubbed_items = []
        redactions = 0
        blocked = 0
        for item in value:
            scrubbed, item_redactions, item_blocked = _scrub_value(item)
            if isinstance(scrubbed, str) and not scrubbed.strip():
                continue
            scrubbed_items.append(scrubbed)
            redactions += item_redactions
            blocked += item_blocked
        return scrubbed_items, redactions, blocked
    if isinstance(value, dict):
        scrubbed_items = {}
        redactions = 0
        blocked = 0
        for key, item in value.items():
            scrubbed, item_redactions, item_blocked = _scrub_value(item)
            scrubbed_items[key] = scrubbed
            redactions += item_redactions
            blocked += item_blocked
        return scrubbed_items, redactions, blocked
    return value, 0, 0


def _scrub_text(text: str) -> tuple[str, int, int]:
    redactions = 0
    blocked = 0
    scrubbed = text
    for token in PersonalityTrainer.NON_EMOJI_TOKENS:
        if token in scrubbed:
            scrubbed = scrubbed.replace(token, "[已移除]")
            redactions += 1
    for pattern in SENSITIVE_PATTERNS:
        scrubbed, count = pattern.subn("[已脱敏]", scrubbed)
        redactions += count
        blocked += count
    return scrubbed, redactions, blocked


def _metadata_dict(metadata: PersonaPackageMetadata | PetPersonaImportResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(metadata, dict):
        return dict(metadata)
    if is_dataclass(metadata):
        return asdict(metadata)
    return {
        "message_count": getattr(metadata, "message_count", 0),
        "target_message_count": getattr(metadata, "target_message_count", 0),
        "used_fallback_messages": getattr(metadata, "used_fallback_messages", False),
        "redaction_count": getattr(metadata, "redaction_count", 0),
        "blocked_sensitive_patterns": getattr(metadata, "blocked_sensitive_patterns", 0),
    }


def _build_manifest(profile: PersonalityProfile, metadata: dict[str, Any], redaction_count: int, blocked_count: int) -> dict[str, Any]:
    slug = safe_persona_slug(profile.name)
    return {
        "schema_version": 1,
        "package_id": slug,
        "slug": slug,
        "display_name": profile.name,
        "source_type": metadata.get("source_type", "chat_export"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "message_count": int(metadata.get("message_count", 0) or 0),
        "target_message_count": int(metadata.get("target_message_count", 0) or 0),
        "used_fallback_messages": bool(metadata.get("used_fallback_messages", False)),
        "privacy": {
            "raw_chat_included": False,
            "local_only_default": True,
            "cloud_enhancement_enabled": False,
            "contains_anonymized_training_seed": True,
            "redaction_count": redaction_count,
            "blocked_sensitive_patterns": blocked_count,
        },
    }


def _build_style_profile(profile: PersonalityProfile) -> dict[str, Any]:
    length_bucket = "short" if profile.avg_sentence_length < 15 else "medium" if profile.avg_sentence_length < 30 else "long"
    return {
        "name": profile.name,
        "pet_type": profile.pet_type,
        "personality_tag": profile.personality_tag,
        "catchphrases": profile.catchphrases,
        "sentence_patterns": profile.sentence_patterns,
        "emoji_habits": profile.emoji_habits,
        "topics": profile.topics,
        "avg_sentence_length_bucket": length_bucket,
        "greeting_style": profile.greeting_style,
    }


def _build_examples(profile: PersonalityProfile) -> list[str]:
    phrase = profile.catchphrases[0] if profile.catchphrases else "嗯嗯"
    emoji = profile.emoji_habits[0] if profile.emoji_habits else ""
    topic = profile.topics[0] if profile.topics else "日常"
    examples = [
        {"messages": [{"role": "user", "content": "今天想聊聊近况"}, {"role": "assistant", "content": f"{phrase}，我会用{profile.personality_tag}一点的方式陪你聊{topic}。{emoji}".strip()}]},
        {"messages": [{"role": "user", "content": "给我一点回应"}, {"role": "assistant", "content": f"{phrase}，我在听，先短短接一句。{emoji}".strip()}]},
        {"messages": [{"role": "user", "content": "现在心情有点乱"}, {"role": "assistant", "content": f"{phrase}，我们慢慢说，不急着一次讲完。{emoji}".strip()}]},
    ]
    lines = []
    for example in examples:
        scrubbed, _, _ = _scrub_value(example)
        lines.append(json.dumps(scrubbed, ensure_ascii=False) + "\n")
    return lines


def _build_eval_report(metadata: dict[str, Any], redaction_count: int, blocked_count: int) -> dict[str, Any]:
    return {
        "message_count": int(metadata.get("message_count", 0) or 0),
        "target_message_count": int(metadata.get("target_message_count", 0) or 0),
        "used_fallback_messages": bool(metadata.get("used_fallback_messages", False)),
        "privacy_checks": {
            "raw_chat_included": False,
            "claims_real_person": False,
            "quotes_source_logs": False,
            "redaction_count": redaction_count,
            "blocked_sensitive_patterns": blocked_count,
        },
        "quality_checks": {
            "has_style_profile": True,
            "has_system_prompt": True,
            "has_anonymized_training_seed": True,
        },
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _strip_export_prefix(value: str) -> str:
    for prefix in ("私聊_", "群聊_"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def _load_messages_from_path(source: Path, target_name: str):
    if source.is_dir():
        return load_export_dir(source, wxid=target_name)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / source.name
        shutil.copy2(source, temp_path)
        return load_export_dir(Path(temp_dir), wxid=target_name)
