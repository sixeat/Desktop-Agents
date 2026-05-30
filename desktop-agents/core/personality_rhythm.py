from dataclasses import dataclass
import random


@dataclass(frozen=True)
class RhythmProfile:
    personality_tag: str
    interval_ms: int
    chars_per_update: int
    jitter: float
    min_chat_interval_s: int
    max_chat_interval_s: int
    max_reply_length: int
    min_thinking_ms: int
    max_thinking_ms: int


RHYTHM_TABLE = {
    "活泼": RhythmProfile("活泼", 35, 1, 0.30, 10, 25, 30, 250, 700),
    "毒舌": RhythmProfile("毒舌", 50, 1, 0.50, 12, 30, 25, 350, 900),
    "温柔": RhythmProfile("温柔", 120, 1, 0.10, 20, 50, 40, 700, 1400),
    "沉稳": RhythmProfile("沉稳", 80, 1, 0.15, 15, 40, 50, 600, 1200),
}


DEFAULT_RHYTHM = RHYTHM_TABLE["活泼"]


def get_rhythm(personality_tag: str | None) -> RhythmProfile:
    return RHYTHM_TABLE.get(personality_tag or "", DEFAULT_RHYTHM)


def _jittered(value: int, jitter: float) -> int:
    if jitter <= 0:
        return value
    return max(1, round(value * random.uniform(1 - jitter, 1 + jitter)))


def get_typing_delay(personality_tag: str | None) -> int:
    rhythm = get_rhythm(personality_tag)
    return _jittered(rhythm.interval_ms, rhythm.jitter)


def get_chat_interval(personality_tag: str | None) -> int:
    rhythm = get_rhythm(personality_tag)
    return random.randint(rhythm.min_chat_interval_s * 1000, rhythm.max_chat_interval_s * 1000)


def get_thinking_time(personality_tag: str | None) -> int:
    rhythm = get_rhythm(personality_tag)
    return random.randint(rhythm.min_thinking_ms, rhythm.max_thinking_ms)
