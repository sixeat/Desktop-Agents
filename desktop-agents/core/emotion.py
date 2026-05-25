from dataclasses import dataclass, field

from core.pet import PetMood


@dataclass(frozen=True)
class EmotionSignal:
    event_type: str
    text: str = ""
    intensity: float = 1.0


@dataclass(frozen=True)
class EmotionState:
    mood: PetMood
    reason: str = ""
    score: dict[str, float] = field(default_factory=dict)


class EmotionEngine:
    KEYWORDS = {
        PetMood.HAPPY: ["哈哈", "开心", "好耶", "喜欢", "谢谢", "可爱", "抱抱", "摸摸", "棒", "爱", "不错"],
        PetMood.SAD: ["难过", "伤心", "委屈", "哭", "糟糕", "不好", "失落", "孤单", "唉"],
        PetMood.SLEEPY: ["困", "累", "晚安", "睡觉", "休息", "疲惫", "想睡"],
        PetMood.ANGRY: ["烦", "生气", "讨厌", "笨", "坏", "走开", "气死", "不理你"],
        PetMood.SURPRISED: ["哇", "真的假的", "震惊", "突然", "什么", "为什么", "怎么会"],
    }

    def analyze(self, signal: EmotionSignal, current: EmotionState | None = None, personality_tag: str = "活泼") -> EmotionState:
        if signal.event_type == "click":
            return EmotionState(PetMood.HAPPY, "被点击互动", {PetMood.HAPPY.value: signal.intensity})
        if signal.event_type == "greeting":
            return EmotionState(PetMood.HAPPY, "主动打招呼", {PetMood.HAPPY.value: signal.intensity})
        if signal.event_type == "manual" and signal.text:
            mood = PetMood(signal.text)
            return EmotionState(mood, "手动切换情绪", {mood.value: signal.intensity})

        score = self._score_text(signal.text)
        self._apply_personality(score, personality_tag)
        if not score:
            mood = current.mood if current is not None else PetMood.NORMAL
            return EmotionState(mood, "未检测到明显情绪", {mood.value: 0.0})

        mood_value, value = max(score.items(), key=lambda item: item[1])
        if value <= 0:
            mood = current.mood if current is not None else PetMood.NORMAL
            return EmotionState(mood, "未检测到明显情绪", {mood.value: value})
        mood = PetMood(mood_value)
        return EmotionState(mood, f"根据{signal.event_type}内容识别为{mood.value}", score)

    def mood_for_text(self, text: str, personality_tag: str = "活泼") -> PetMood:
        return self.analyze(EmotionSignal("chat", text), personality_tag=personality_tag).mood

    def decay(self, current: EmotionState) -> EmotionState:
        if current.mood in {PetMood.HAPPY, PetMood.SAD, PetMood.ANGRY, PetMood.SURPRISED}:
            return EmotionState(PetMood.NORMAL, "情绪自然回落", {PetMood.NORMAL.value: 1.0})
        return current

    def mood_prompt(self, mood: PetMood, personality_tag: str = "活泼") -> str:
        prompts = {
            PetMood.NORMAL: "当前情绪自然平稳，说话轻松日常。",
            PetMood.HAPPY: "当前情绪开心，语气更亲近、轻快，可以带一点撒娇。",
            PetMood.SAD: "当前有点难过，说话更软、更需要陪伴和安慰。",
            PetMood.SLEEPY: "当前有点困困，说话更短、更软、更慢。",
            PetMood.ANGRY: "当前有点不高兴，可以轻微别扭，但不能攻击或伤害用户。",
            PetMood.SURPRISED: "当前很惊讶，回应里自然表现出意外和好奇。",
        }
        modifier = {
            "温柔": "保持温柔安抚，不要过激。",
            "毒舌": "可以嘴硬吐槽，但本质要关心用户。",
            "傲娇": "可以嘴硬，但不要否认陪伴用户。",
            "沉稳": "表达要稳重克制。",
            "活泼": "可以更有元气。",
        }.get(personality_tag, "")
        return f"{prompts.get(mood, prompts[PetMood.NORMAL])}{modifier}"

    def _score_text(self, text: str) -> dict[str, float]:
        score = {mood.value: 0.0 for mood in [PetMood.HAPPY, PetMood.SAD, PetMood.SLEEPY, PetMood.ANGRY, PetMood.SURPRISED]}
        for mood, keywords in self.KEYWORDS.items():
            score[mood.value] += sum(text.count(keyword) for keyword in keywords)
        if text.count("!") + text.count("！") >= 2 or text.count("?") + text.count("？") >= 2:
            score[PetMood.SURPRISED.value] += 1.5
        return {mood: value for mood, value in score.items() if value > 0}

    def _apply_personality(self, score: dict[str, float], personality_tag: str) -> None:
        if personality_tag == "活泼":
            score[PetMood.HAPPY.value] = score.get(PetMood.HAPPY.value, 0.0) * 1.25
            score[PetMood.SURPRISED.value] = score.get(PetMood.SURPRISED.value, 0.0) * 1.15
        elif personality_tag == "温柔":
            angry = score.get(PetMood.ANGRY.value, 0.0) * 0.2
            score[PetMood.ANGRY.value] = angry
            if angry > 0:
                score[PetMood.SAD.value] = max(score.get(PetMood.SAD.value, 0.0), angry + 0.1)
        elif personality_tag in {"毒舌", "傲娇"}:
            score[PetMood.ANGRY.value] = score.get(PetMood.ANGRY.value, 0.0) * 1.2
            score[PetMood.HAPPY.value] = score.get(PetMood.HAPPY.value, 0.0) * 1.1
        elif personality_tag == "沉稳":
            for mood in list(score):
                score[mood] *= 0.75
