import re
from collections import Counter
from statistics import median

from tools.wechat.models import ChatMessage

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
TOKEN_RE = re.compile(r"[一-鿿]{2,}|[A-Za-z][A-Za-z0-9_+#.-]{1,}")

TOPIC_KEYWORDS = {
    "工作": ["工作", "项目", "需求", "会议", "客户", "同事", "老板", "汇报", "排期"],
    "学习": ["学习", "考试", "课程", "作业", "论文", "老师", "学校", "复习"],
    "技术": ["代码", "bug", "接口", "数据库", "服务器", "python", "java", "ai", "模型", "部署", "日志"],
    "生活": ["吃饭", "睡觉", "周末", "天气", "家里", "电影", "晚安", "早安", "今天"],
    "财务": ["钱", "工资", "房贷", "股票", "基金", "转账", "红包", "价格"],
    "旅行": ["旅游", "酒店", "机票", "高铁", "出差", "景点", "机场"],
    "游戏": ["游戏", "开黑", "王者", "原神", "排位", "队友"],
    "健康": ["医院", "医生", "感冒", "运动", "健身", "药", "睡眠"],
}

STOP_WORDS = {"这个", "那个", "就是", "然后", "还是", "可以", "不是", "没有", "一下", "感觉", "什么", "怎么"}


def build_personality(messages: list[ChatMessage], wxid: str, display_name: str | None = None) -> dict[str, object]:
    target_messages = [msg for msg in messages if msg.is_from_target] or messages
    texts = [_normalize_text(msg.content) for msg in target_messages]
    texts = [text for text in texts if len(text) >= 2]
    lengths = [len(text) for text in texts]
    message_count = len(texts)

    avg_length = sum(lengths) / message_count if message_count else 0
    median_length = median(lengths) if lengths else 0
    question_ratio = _ratio(texts, lambda text: "?" in text or "？" in text)
    exclamation_ratio = _ratio(texts, lambda text: "!" in text or "！" in text)
    ellipsis_ratio = _ratio(texts, lambda text: "..." in text or "……" in text or "~" in text)
    short_ratio = _ratio(texts, lambda text: len(text) <= 6)
    long_ratio = _ratio(texts, lambda text: len(text) >= 60)
    laughter_ratio = _ratio(texts, lambda text: any(marker in text.lower() for marker in ("哈哈", "笑死", "hh", "233")))
    modal_ratio = _ratio(texts, lambda text: any(marker in text for marker in ("呀", "啦", "呢", "嘛", "哦", "哈")))
    emoji_ratio = _ratio(texts, lambda text: bool(EMOJI_RE.search(text)))

    style = _build_style(short_ratio, question_ratio, exclamation_ratio, ellipsis_ratio, long_ratio, laughter_ratio, modal_ratio)
    topics = _detect_topics(texts)
    tone = _detect_tone(laughter_ratio, exclamation_ratio, modal_ratio, emoji_ratio, texts)
    reply_speed = _detect_reply_speed(short_ratio, long_ratio, median_length)
    emoji_frequency = _detect_emoji_frequency(emoji_ratio)
    common_phrases = _common_phrases(texts)
    for phrase in common_phrases:
        if phrase not in style and len(style) < 8:
            style.append(phrase)

    name = display_name or f"微信人格_{_safe_suffix(wxid)}"
    description = (
        f"从本地微信聊天记录中提取的人格：共分析{message_count}条文本消息，"
        f"平均每条约{avg_length:.1f}字，语气偏{tone}，常围绕{'、'.join(topics[:3])}交流。"
    )

    return {
        "name": name,
        "description": description,
        "style": style or ["自然口语", "简洁交流"],
        "topics": topics,
        "reply_speed": reply_speed,
        "emoji_frequency": emoji_frequency,
        "tone": tone,
        "avatar": "",
        "system_prompt": "",
    }


def summarize_messages(messages: list[ChatMessage]) -> dict[str, object]:
    target_count = sum(1 for msg in messages if msg.is_from_target)
    return {
        "total_messages": len(messages),
        "target_messages": target_count,
        "sources": sorted({msg.source for msg in messages}),
    }


def _normalize_text(text: str) -> str:
    return URL_RE.sub("", text).strip()


def _ratio(texts: list[str], predicate) -> float:
    if not texts:
        return 0.0
    return sum(1 for text in texts if predicate(text)) / len(texts)


def _build_style(short_ratio, question_ratio, exclamation_ratio, ellipsis_ratio, long_ratio, laughter_ratio, modal_ratio) -> list[str]:
    style: list[str] = []
    if short_ratio > 0.45:
        style.append("回复简短")
    if question_ratio > 0.2:
        style.append("常用提问推进对话")
    if exclamation_ratio > 0.15:
        style.append("表达热情直接")
    if ellipsis_ratio > 0.12:
        style.append("语气轻松")
    if long_ratio > 0.2:
        style.append("喜欢展开解释")
    if laughter_ratio > 0.08:
        style.append("幽默调侃")
    if modal_ratio > 0.15:
        style.append("口语化自然")
    return style or ["自然口语", "简洁交流"]


def _detect_topics(texts: list[str]) -> list[str]:
    joined = "\n".join(texts).lower()
    scores = Counter()
    for topic, keywords in TOPIC_KEYWORDS.items():
        scores[topic] = sum(joined.count(keyword.lower()) for keyword in keywords)
    topics = [topic for topic, score in scores.most_common(5) if score > 0]
    return topics or ["日常聊天", "生活琐事", "轻松交流"]


def _detect_tone(laughter_ratio, exclamation_ratio, modal_ratio, emoji_ratio, texts: list[str]) -> str:
    joined = "\n".join(texts)
    if laughter_ratio > 0.08:
        return "幽默"
    if modal_ratio > 0.2 or emoji_ratio > 0.15:
        return "活泼"
    if any(word in joined for word in ("没事", "辛苦", "加油", "抱抱", "慢慢来")):
        return "温柔"
    if any(word.lower() in joined.lower() for word in ("代码", "bug", "接口", "数据库", "逻辑")):
        return "理性"
    if exclamation_ratio > 0.18:
        return "热情"
    return "自然"


def _detect_reply_speed(short_ratio, long_ratio, median_length) -> str:
    if short_ratio > 0.5 and median_length <= 10:
        return "fast"
    if long_ratio > 0.25 or median_length >= 35:
        return "slow"
    return "normal"


def _detect_emoji_frequency(emoji_ratio) -> str:
    if emoji_ratio >= 0.2:
        return "high"
    if emoji_ratio >= 0.05:
        return "medium"
    return "low"


def _common_phrases(texts: list[str]) -> list[str]:
    tokens = []
    for text in texts:
        tokens.extend(token for token in TOKEN_RE.findall(text) if token not in STOP_WORDS and len(token) <= 8)
    phrases = []
    for token, count in Counter(tokens).most_common(5):
        if count >= 2:
            phrases.append(f"常说“{token}”")
    return phrases


def _safe_suffix(wxid: str) -> str:
    return "".join(ch for ch in wxid if ch.isalnum() or ch in "_- ").strip()[:16] or "unknown"
