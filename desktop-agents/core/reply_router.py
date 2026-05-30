import inspect
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Literal

from core.emotion import EmotionSignal

from core.llm_client import OpenAICompatibleClient
from core.llm_settings import ROUTE_MODE_LOCAL_ONLY, has_api_key, load_llm_settings, load_reply_route_mode, settings_to_client_kwargs
from core.pet_companion import PetCompanion, PetResponse

ReplyRoute = Literal["cloud", "local"]
StreamEvent = tuple[Literal["partial", "final"], str | PetResponse]


@dataclass(frozen=True)
class ReplyRequest:
    text: str
    channel: str
    event_type: str
    companion: PetCompanion
    memory_context: str = ""
    force_route: ReplyRoute | None = None


@dataclass(frozen=True)
class RouteDecision:
    route: ReplyRoute
    reason: str
    is_deep_topic: bool
    has_api_key: bool


def is_deep_topic(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) >= 80:
        return True
    indicators = [
        "为什么",
        "分析",
        "计划",
        "怎么解决",
        "比较",
        "总结",
        "代码",
        "方案",
        "架构",
        "设计",
        "原因",
        "推理",
    ]
    if any(indicator in stripped for indicator in indicators):
        return True
    sentence_marks = sum(stripped.count(mark) for mark in ["。", "？", "！", "\n", ".", "?", "!"])
    return sentence_marks >= 2


class LocalReplyBackend:
    def __init__(self, engine=None):
        self.engine = engine

    async def reply(self, request: ReplyRequest) -> PetResponse:
        return request.companion.handle_interaction(request.event_type, request.text)


class CloudReplyBackend:
    def __init__(self, client_factory: Callable[[], object] | None = None):
        self.client_factory = client_factory

    def _create_client(self):
        if self.client_factory is not None:
            return self.client_factory()
        return OpenAICompatibleClient(**settings_to_client_kwargs(load_llm_settings()))

    async def reply(self, request: ReplyRequest) -> PetResponse:
        client = self._create_client()
        try:
            return await request.companion.chat(
                request.text,
                client=client,
                memory_context=request.memory_context,
            )
        finally:
            await self._close_client(client)

    async def reply_stream(self, request: ReplyRequest) -> AsyncIterator[StreamEvent]:
        companion = request.companion
        companion.emotion_state = companion.emotion_engine.analyze(
            EmotionSignal("chat", request.text),
            companion.emotion_state,
            companion.profile.personality_tag,
        )
        mood = companion.emotion_state.mood
        reason = companion.emotion_state.reason
        client = self._create_client()
        full_text = ""
        try:
            messages = companion.build_messages(request.text, mood, request.memory_context)
            async for chunk in client.chat_stream(messages):
                full_text += str(chunk)
                if full_text.strip():
                    yield "partial", full_text
            clean_reply = full_text.strip()
            if not clean_reply:
                clean_reply = companion.local_reply(request.text, mood)
                reason = "LLM空回复，使用本地回复"
                source = "local"
            else:
                source = "llm"
            companion.remember_exchange(request.text, clean_reply)
            yield "final", PetResponse(clean_reply, mood, source, reason)
        except Exception:
            reply = companion.local_reply(request.text, companion.emotion_state.mood)
            companion.remember_exchange(request.text, reply)
            yield "final", PetResponse(reply, companion.emotion_state.mood, "local", "LLM流式失败，使用本地回复")
        finally:
            await self._close_client(client)

    async def _close_client(self, client) -> None:
        close = getattr(client, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result


class ReplyRouter:
    def __init__(
        self,
        api_key_available: Callable[[], bool] = has_api_key,
        cloud_backend: CloudReplyBackend | None = None,
        local_backend: LocalReplyBackend | None = None,
        route_mode_provider: Callable[[], str] = load_reply_route_mode,
    ):
        self.api_key_available = api_key_available
        self.cloud_backend = cloud_backend or CloudReplyBackend()
        self.local_backend = local_backend or LocalReplyBackend()
        self.route_mode_provider = route_mode_provider

    def decide(self, request: ReplyRequest) -> RouteDecision:
        key_available = bool(self.api_key_available())
        deep_topic = is_deep_topic(request.text)
        if request.force_route is not None:
            return RouteDecision(request.force_route, f"forced_{request.force_route}", deep_topic, key_available)
        if self.route_mode_provider() == ROUTE_MODE_LOCAL_ONLY:
            return RouteDecision("local", "mode_local_only", deep_topic, key_available)
        if not key_available:
            return RouteDecision("local", "missing_api_key", deep_topic, key_available)
        return RouteDecision("cloud", "api_key_available_current_compat", deep_topic, key_available)

    async def reply(self, request: ReplyRequest) -> PetResponse:
        decision = self.decide(request)
        if decision.route == "cloud":
            return await self.cloud_backend.reply(request)
        return await self.local_backend.reply(request)
