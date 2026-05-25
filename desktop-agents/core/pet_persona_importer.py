import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from core.personality_trainer import PersonalityProfile, PersonalityTrainer
from tools.wechat.parsers import load_export_dir


@dataclass(frozen=True)
class PetPersonaImportResult:
    profile: PersonalityProfile
    message_count: int
    target_message_count: int
    used_fallback_messages: bool


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
            output_path = save_pet_persona(profile, Path(output_dir) / safe_persona_slug(persona_name) / "persona.json")
        results.append(BatchPersonaResult(profile, persona_name, source_names, len(messages), output_path))
    return results


def save_pet_persona(profile: PersonalityProfile, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    PersonalityTrainer().save(profile, output_path)
    return output_path


def safe_persona_slug(value: str) -> str:
    safe = "".join(ch for ch in value.strip() if ch.isalnum() or ch in "_- ").strip().replace(" ", "_")
    return safe[:64] or "persona"


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
