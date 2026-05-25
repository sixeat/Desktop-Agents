import json
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

from config import DESKTOP_AGENTS_CONFIG_PATH
from core.pet import PetConfig, default_pet_definition, default_personality_for_type


def new_agent_id() -> str:
    return uuid4().hex


def normalize_pet_config(config: PetConfig) -> PetConfig:
    color = tuple(int(value) for value in config.color[:3])
    mood_avatar_paths = {str(key): str(value) for key, value in (config.mood_avatar_paths or {}).items() if value}
    avatar_path = config.avatar_path or mood_avatar_paths.get("normal")
    default_definition = default_pet_definition()
    return replace(
        config,
        type_id=config.type_id or default_definition.type_id,
        type_name=config.type_name or default_definition.display_name,
        color=color,
        personality_tag=config.personality_tag or default_personality_for_type(config.type_id or default_definition.type_id),
        agent_id=config.agent_id or new_agent_id(),
        avatar_path=avatar_path,
        mood_avatar_paths=mood_avatar_paths,
    )


def load_pet_configs(path: str | Path = DESKTOP_AGENTS_CONFIG_PATH) -> list[PetConfig]:
    config_path = Path(path)
    if not config_path.exists():
        return []
    data = json.loads(config_path.read_text(encoding="utf-8"))
    agents = data.get("agents", []) if isinstance(data, dict) else []
    configs = []
    for item in agents:
        if not isinstance(item, dict):
            continue
        try:
            configs.append(normalize_pet_config(_config_from_dict(item)))
        except (KeyError, TypeError, ValueError):
            continue
    return configs


def save_pet_configs(configs: list[PetConfig], path: str | Path = DESKTOP_AGENTS_CONFIG_PATH) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "agents": [_config_to_dict(normalize_pet_config(config)) for config in configs]}
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _config_from_dict(data: dict) -> PetConfig:
    default_definition = default_pet_definition()
    type_id = str(data.get("type_id") or default_definition.type_id)
    return PetConfig(
        type_id=type_id,
        type_name=str(data.get("type_name") or default_definition.display_name),
        name=str(data["name"]),
        color=tuple(data["color"]),
        personality_tag=str(data.get("personality_tag") or default_personality_for_type(type_id)),
        agent_id=str(data.get("agent_id") or ""),
        avatar_path=data.get("avatar_path"),
        persona_path=data.get("persona_path"),
        mood_avatar_paths=dict(data.get("mood_avatar_paths") or {}),
    )

def _config_to_dict(config: PetConfig) -> dict:
    data = asdict(config)
    data["color"] = list(config.color)
    return data
