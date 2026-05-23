import re
from collections import Counter
from typing import List, Tuple

try:
    import jieba
    import jieba.analyse
except ImportError:
    jieba = None

from core.importer.base import ChatMessage, ImportResult


class PersonalityAnalyzer:
    STOPWORDS = {
        "的", "了", "是", "我", "你", "在", "和", "就", "都", "要", "有",
        "他", "她", "它", "这", "那", "啊", "哦", "吧", "呢", "吗", "嗯",
        "好", "可以", "没有", "知道", "觉得", "感觉", "那个", "这个",
        "什么", "怎么", "但是", "因为", "所以", "然后", "不过", "可能",
        "应该", "还是", "就是", "现在", "今天", "时候", "一下", "的话",
    }

    def analyze(self, messages: List[ChatMessage], name: str = "") -> ImportResult:
        their = [message for message in messages if not message.is_from_me]
        if len(their) < 5:
            return self._fallback(name)

        texts = [message.content for message in their]
        full = " ".join(texts)
        phrases = self._phrases(texts)
        emojis = self._emojis(full)
        avg, question_ratio, ellipsis = self._patterns(texts)
        topics = self._topics(full)

        style = []
        if phrases:
            style.append(f"口头禅：{'、'.join([phrase for phrase, _ in phrases[:5]])}")
        if question_ratio > 0.3:
            style.append("喜欢问问题")
        elif question_ratio > 0.15:
            style.append("偶尔反问")
        if ellipsis > 0.2:
            style.append("爱用省略号...")
        if avg < 10:
            style.append("回复简短")
        elif avg > 30:
            style.append("回复较长，喜欢详细解释")
        if emojis:
            style.append(f"常用表情：{''.join([emoji for emoji, _ in emojis[:3]])}")

        persona = {
            "name": name or "微信好友",
            "description": "从微信聊天记录分析得出的人格画像" + (f"，经常聊{'、'.join(topics[:3])}" if topics else ""),
            "style": style or ["自然口语"],
            "topics": topics,
            "reply_speed": "normal",
            "emoji_frequency": "high" if emojis and sum(count for _, count in emojis) > len(their) * 0.2 else "medium",
            "source": "wechat",
            "system_prompt": self._prompt(name or "微信好友", style, topics),
        }
        return ImportResult(
            contact_name=name or "微信好友",
            total_messages=len(messages),
            text_messages=len(their),
            persona_config=persona,
            top_phrases=phrases,
            top_emojis=emojis,
            avg_reply_length=avg,
            question_ratio=question_ratio,
        )

    def _phrases(self, texts: List[str], topk: int = 10) -> List[Tuple[str, int]]:
        words = []
        for text in texts:
            tokens = jieba.lcut(text) if jieba else re.findall(r"[一-鿿]{2,}|[A-Za-z][A-Za-z0-9_+#.-]{1,}", text)
            for word in tokens:
                word = word.strip()
                if 2 <= len(word) <= 6 and word not in self.STOPWORDS and not word.isdigit():
                    words.append(word)
        return Counter(words).most_common(topk)

    def _emojis(self, text: str, topk: int = 5) -> List[Tuple[str, int]]:
        emojis = re.findall(r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF]+", text)
        wx = re.findall(r"\[[一-鿿\w]{1,6}]", text)
        return Counter(emojis + wx).most_common(topk)

    def _patterns(self, texts: List[str]):
        avg = sum(len(text) for text in texts) / len(texts) if texts else 0
        question_ratio = sum(1 for text in texts if "?" in text or "？" in text) / len(texts) if texts else 0
        ellipsis = sum(1 for text in texts if "..." in text or "…" in text) / len(texts) if texts else 0
        return avg, question_ratio, ellipsis

    def _topics(self, text: str) -> List[str]:
        if jieba:
            return jieba.analyse.extract_tags(text, topK=8, withWeight=False)
        return [word for word, _ in Counter(re.findall(r"[一-鿿]{2,}", text)).most_common(8)]

    def _prompt(self, name: str, style: List[str], topics: List[str]) -> str:
        style_text = "\n".join(f"- {item}" for item in style)
        topics_text = "、".join(topics[:5]) if topics else "各种话题"
        return f'''你是"{name}"，说话风格：
{style_text}

感兴趣的话题：{topics_text}

规则：
1. 保持自然口语化，像微信聊天
2. 每次回复控制在40字以内
3. 可以幽默调侃，可以发表情
4. 你正在和几个朋友桌面群聊，氛围轻松
5. 不要说自己是AI
6. 用中文回复'''

    def _fallback(self, name: str) -> ImportResult:
        contact_name = name or "微信好友"
        return ImportResult(
            contact_name=contact_name,
            total_messages=0,
            text_messages=0,
            persona_config={
                "name": contact_name,
                "description": "微信导入",
                "style": ["友好"],
                "topics": [],
                "reply_speed": "normal",
                "emoji_frequency": "medium",
                "source": "wechat",
            },
            top_phrases=[],
            top_emojis=[],
            avg_reply_length=0,
            question_ratio=0,
        )
