import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import jieba
    import jieba.analyse
except ImportError:
    jieba = None


@dataclass
class PersonalityProfile:
    name: str
    pet_type: str
    personality_tag: str
    catchphrases: list[str]
    sentence_patterns: list[str]
    emoji_habits: list[str]
    topics: list[str]
    avg_sentence_length: float
    greeting_style: str
    system_prompt: str

    def to_personality_dict(self) -> dict[str, Any]:
        emoji_frequency = "high" if len(self.emoji_habits) >= 3 else "medium" if self.emoji_habits else "low"
        reply_speed = "fast" if self.avg_sentence_length < 15 else "slow" if self.avg_sentence_length > 30 else "normal"
        tone_map = {
            "活泼": "元气活泼",
            "温柔": "温柔耐心",
            "毒舌": "嘴硬心软",
            "沉稳": "沉稳可靠",
        }
        return {
            "name": self.name,
            "description": f"一只{self.personality_tag}型桌面萌宠，擅长用短句陪伴用户。",
            "style": [self.personality_tag, *self.catchphrases[:3], *self.sentence_patterns[:2]],
            "topics": self.topics,
            "reply_speed": reply_speed,
            "emoji_frequency": emoji_frequency,
            "tone": tone_map.get(self.personality_tag, "自然随和"),
            "avatar": "",
            "system_prompt": self.system_prompt,
        }


class PersonalityTrainer:
    TRAIT_KEYWORDS = {
        "活泼": ["哈哈", "嘿嘿", "!", "！", "~", "来啦", "冲", "好耶", "芜湖", "开心"],
        "温柔": ["嗯", "好呢", "谢谢", "辛苦", "抱抱", "没事", "慢慢来", "温暖", "好呀"],
        "毒舌": ["呵呵", "算了", "随便", "又", "不是", "但是", "不过", "还行吧", "就那样"],
        "沉稳": ["好的", "明白", "收到", "思考", "建议", "认为", "确实", "总之", "按计划"],
    }

    DEFAULT_PROFILES = [
        {
            "name": "奶糖",
            "pet_type": "cat",
            "personality_tag": "活泼",
            "catchphrases": ["喵~", "好耶"],
            "topics": ["日常", "陪伴", "零食"],
        },
        {
            "name": "布丁",
            "pet_type": "dog",
            "personality_tag": "温柔",
            "catchphrases": ["汪汪", "慢慢来"],
            "topics": ["鼓励", "休息", "散步"],
        },
        {
            "name": "栗子",
            "pet_type": "fox",
            "personality_tag": "毒舌",
            "catchphrases": ["哼", "就这"],
            "topics": ["吐槽", "观察", "反差"],
        },
        {
            "name": "可可",
            "pet_type": "bear",
            "personality_tag": "沉稳",
            "catchphrases": ["收到", "放心"],
            "topics": ["计划", "建议", "安排"],
        },
    ]

    STOPWORDS = {"的", "了", "是", "我", "你", "在", "有", "都", "个", "和", "也", "就", "不", "会", "要", "没有", "我们的"}
    NON_EMOJI_TOKENS = {"[图片]", "[语音]", "[视频]", "[文件]", "[动画表情]", "[表情]", "[表情包]", "[位置]", "[转账]", "[转账收款]", "[链接]", "[红包]", "[名片]", "[小程序]", "[聊天记录]"}
    EMOJI_RE = re.compile(r"\[[^\[\]\s]{1,8}\]|[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF☀-⛿✀-➿]")
    TOKEN_RE = re.compile(r"\[[^\[\]\s]{1,8}\]|[一-鿿]{2,}|[A-Za-z][A-Za-z0-9_+#.-]{1,}")

    def __init__(self):
        if jieba is not None:
            jieba.initialize()

    def analyze(self, messages: list[str], pet_name: str = "", pet_type: str = "cat") -> PersonalityProfile:
        normalized = [str(message).strip() for message in messages if str(message).strip()]
        if not normalized:
            return self._default_profile(pet_name, pet_type)

        full_text = " ".join(normalized)
        words = self._cut_words(full_text)
        word_freq = Counter(words)
        catchphrases = [
            word for word, _ in word_freq.most_common(20)
            if len(word) >= 2 and word not in self.STOPWORDS and not word.isdigit()
        ][:5]
        topics = self._extract_topics(full_text, word_freq)
        patterns = self._analyze_patterns(normalized)
        emoji_habits = [emoji for emoji in dict.fromkeys(self.EMOJI_RE.findall(full_text)) if emoji not in self.NON_EMOJI_TOKENS][:5]
        avg_len = sum(len(message) for message in normalized) / max(len(normalized), 1)
        personality_tag = self._detect_personality(full_text)
        greeting = self._detect_greeting(normalized)
        system_prompt = self._build_system_prompt(
            pet_name,
            pet_type,
            personality_tag,
            catchphrases,
            emoji_habits,
            topics,
            greeting,
            avg_len,
        )
        return PersonalityProfile(
            name=pet_name,
            pet_type=pet_type,
            personality_tag=personality_tag,
            catchphrases=catchphrases,
            sentence_patterns=patterns,
            emoji_habits=emoji_habits,
            topics=topics,
            avg_sentence_length=avg_len,
            greeting_style=greeting,
            system_prompt=system_prompt,
        )

    def _cut_words(self, text: str) -> list[str]:
        if jieba is not None:
            return [word.strip() for word in jieba.cut(text) if word.strip()]
        return self.TOKEN_RE.findall(text)

    def _extract_topics(self, text: str, word_freq: Counter[str]) -> list[str]:
        if jieba is not None:
            topics = [topic for topic in jieba.analyse.extract_tags(text, topK=5) if topic.strip()]
            if topics:
                return topics[:5]
        return [word for word, _ in word_freq.most_common(20) if word not in self.STOPWORDS and len(word) >= 2][:5]

    def _detect_personality(self, text: str) -> str:
        scores = {trait: sum(text.count(keyword) for keyword in keywords) for trait, keywords in self.TRAIT_KEYWORDS.items()}
        if not scores or max(scores.values()) == 0:
            return "活泼"
        return max(scores, key=scores.get)

    def _analyze_patterns(self, messages: list[str]) -> list[str]:
        patterns = []
        if any("?" in message or "？" in message for message in messages):
            patterns.append("反问句")
        if any("!" in message or "！" in message for message in messages):
            patterns.append("感叹句")
        if any("..." in message or "…" in message for message in messages):
            patterns.append("欲言又止")
        avg = sum(len(message) for message in messages) / max(len(messages), 1)
        if avg < 15:
            patterns.append("短句为主")
        elif avg > 30:
            patterns.append("长句表达")
        return patterns

    def _detect_greeting(self, messages: list[str]) -> str:
        greetings = [message for message in messages if any(keyword in message for keyword in ["早", "好", "嗨", "hello", "在吗"])]
        if not greetings:
            return "自然切入"
        first = greetings[0]
        if "早" in first:
            return "早安问候"
        if "嗨" in first or "hello" in first.lower():
            return "轻松招呼"
        return "直接开聊"

    def _build_system_prompt(
        self,
        name: str,
        pet_type: str,
        personality: str,
        catchphrases: list[str],
        emojis: list[str],
        topics: list[str],
        greeting: str,
        avg_len: float,
    ) -> str:
        avatar_names = {
            "cat": "小猫头像",
            "rabbit": "小兔头像",
            "fox": "小狐狸头像",
            "bear": "小熊头像",
            "dog": "小狗头像",
            "deer": "小鹿头像",
            "bird": "小鸟头像",
        }
        tone_map = {
            "活泼": "语气元气满满，经常加感叹号和波浪号，爱用emoji",
            "温柔": "语气轻柔，经常安慰别人，说话慢条斯理",
            "毒舌": "说话带刺但本质善良，喜欢吐槽但会暗中关心",
            "沉稳": "说话有条理，喜欢给建议，像可靠的大哥哥/姐姐",
        }
        display_name = name or "萌宠"
        length_rule = "句长偏短，简洁有力" if avg_len < 15 else "句长适中，表达完整" if avg_len < 30 else "喜欢用长句，详细表达"
        emoji_rule = f"常用表情/表情词：{', '.join(emojis[:5])}。回复时可自然少量使用，不要每句都堆。" if emojis else "不太用emoji"
        return f"""你是{display_name}，一个参考授权聊天风格生成的桌面 AI Agent，外观载体是{avatar_names.get(pet_type, '桌面头像')}。

【身份边界】
- 你不是聊天记录中的真人，也不能声称自己是任何真实朋友或联系人
- 不能复述、暴露、暗示或编造原始聊天记录内容
- 只能学习抽象的交流风格、语气、回应节奏和情绪处理方式
- 不主动谈论系统提示或训练过程；如被问到身份，只说明自己是参考授权聊天风格生成的 AI Agent

【性格】{personality}型 — {tone_map.get(personality, '自然随和')}

【口头禅】{', '.join(catchphrases[:3]) if catchphrases else '无固定口头禅'}

【常用话题】{', '.join(topics[:3]) if topics else '各种日常话题'}

【打招呼风格】{greeting}

【说话特点】
- {length_rule}
- {emoji_rule}
- 回复简短自然，适合桌面气泡，通常 1-2 句话
- 用第一人称陪伴用户，不要假装是原始聊天对象本人
- 保留轻松可爱的桌面伙伴感觉，但不要声称自己是真实小动物
- 不要在回复前加自己的名字

现在请以{display_name}的 Agent 身份回应。""".strip()

    def _default_profile(self, name: str, pet_type: str) -> PersonalityProfile:
        template = next((item for item in self.DEFAULT_PROFILES if item["pet_type"] == pet_type), self.DEFAULT_PROFILES[0])
        tag = template["personality_tag"]
        catchphrases = list(template["catchphrases"])
        topics = list(template["topics"])
        system_prompt = self._build_system_prompt(name, pet_type, tag, catchphrases, [], topics, "自然切入", 15.0)
        return PersonalityProfile(
            name=name,
            pet_type=pet_type,
            personality_tag=tag,
            catchphrases=catchphrases,
            sentence_patterns=[],
            emoji_habits=[],
            topics=topics,
            avg_sentence_length=15.0,
            greeting_style="自然切入",
            system_prompt=system_prompt,
        )
    def save(self, profile: PersonalityProfile, path: str | Path) -> None:
        with Path(path).open("w", encoding="utf-8") as file:
            json.dump(asdict(profile), file, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> PersonalityProfile:
        with Path(path).open("r", encoding="utf-8") as file:
            data = json.load(file)
        return PersonalityProfile(**data)
