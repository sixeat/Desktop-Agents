from dataclasses import dataclass, field
from enum import StrEnum


class PetMood(StrEnum):
    NORMAL = "normal"
    HAPPY = "happy"
    SAD = "sad"
    SLEEPY = "sleepy"
    ANGRY = "angry"
    SURPRISED = "surprised"


@dataclass(frozen=True)
class PetDefinition:
    type_id: str
    display_name: str
    default_name: str
    color: tuple[int, int, int]


@dataclass(frozen=True)
class PetConfig:
    type_id: str
    type_name: str
    name: str
    color: tuple[int, int, int]
    personality_tag: str = "活泼"
    agent_id: str = ""
    avatar_path: str | None = None
    persona_path: str | None = None
    mood_avatar_paths: dict[str, str] = field(default_factory=dict)

    @property
    def identity(self) -> str:
        return self.agent_id or self.type_id


DEFAULT_PERSONALITY_BY_TYPE = {
    "cat": "活泼",
    "dog": "活泼",
    "rabbit": "温柔",
    "deer": "温柔",
    "fox": "毒舌",
    "bear": "沉稳",
    "bird": "活泼",
}


PERSONALITY_TAGS = ["活泼", "温柔", "毒舌", "沉稳"]


_PET_DEFINITIONS = [
    PetDefinition("cat", "小猫", "奶糖", (255, 141, 161)),
    PetDefinition("dog", "小狗", "布丁", (255, 190, 105)),
    PetDefinition("rabbit", "兔兔", "棉花", (168, 143, 255)),
    PetDefinition("bird", "小鸟", "啾啾", (90, 200, 250)),
    PetDefinition("bear", "小熊", "可可", (181, 136, 99)),
    PetDefinition("fox", "狐狸", "栗子", (255, 128, 64)),
]

DEFAULT_PET_DEFINITION = _PET_DEFINITIONS[0]


def available_pet_definitions() -> list[PetDefinition]:
    return list(_PET_DEFINITIONS)


def default_pet_definition() -> PetDefinition:
    return DEFAULT_PET_DEFINITION


def pet_definition_by_id(type_id: str) -> PetDefinition | None:
    return next((pet for pet in _PET_DEFINITIONS if pet.type_id == type_id), None)


def default_personality_for_type(type_id: str) -> str:
    return DEFAULT_PERSONALITY_BY_TYPE.get(type_id, "活泼")