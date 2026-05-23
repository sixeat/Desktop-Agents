import asyncio
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from core.agent import Agent
from core.builtin_tools import default_sandbox
from core.tooling import ScreenshotRequester, ToolCallRequest, ToolContext, ToolEventCallback, PermissionRequester


@dataclass
class BusMessage:
    sender: str
    content: str
    kind: str = "agent"
    agent_id: str | None = None
    anchor_agent_id: str | None = None
    timestamp: float = field(default_factory=time.time)


class AgentBus:
    def __init__(
        self,
        max_history: int = 20,
        auto_min_seconds: float = 5,
        auto_max_seconds: float = 10,
        followup_probability: float = 0.3,
        rng: random.Random | None = None,
    ):
        self.agents: dict[str, Agent] = {}
        self.recent_history: deque[BusMessage] = deque(maxlen=max_history)
        self.auto_min_seconds = auto_min_seconds
        self.auto_max_seconds = auto_max_seconds
        self.followup_probability = followup_probability
        self._rng = rng or random.Random()
        self._subscribers: list[Callable[[BusMessage], None]] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._conversation_lock: asyncio.Lock | None = None
        self.permission_requester: PermissionRequester | None = None
        self.screenshot_requester: ScreenshotRequester | None = None

    def register(self, agent_id: str, agent: Agent) -> None:
        self.agents[agent_id] = agent

    def unregister(self, agent_id: str) -> None:
        self.agents.pop(agent_id, None)

    def subscribe(self, callback: Callable[[BusMessage], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def unsubscribe():
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def broadcast(self, msg: BusMessage) -> None:
        self.recent_history.append(msg)
        for callback in list(self._subscribers):
            try:
                callback(msg)
            except Exception:
                continue

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(lambda: None)

    def post_user_message(self, content: str, anchor_agent_id: str | None = None) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.handle_user_interjection(content, anchor_agent_id),
                self._loop,
            )
            return

        threading.Thread(
            target=lambda: asyncio.run(self.handle_user_interjection(content, anchor_agent_id)),
            daemon=True,
        ).start()

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._conversation_lock = asyncio.Lock()
        try:
            self._loop.run_until_complete(self._auto_chat_loop())
        finally:
            self._loop.close()
            self._loop = None
            self._conversation_lock = None

    async def _auto_chat_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._rng.uniform(self.auto_min_seconds, self.auto_max_seconds))
            if not self._running:
                break
            await self.run_auto_turn_once()

    async def run_auto_turn_once(self) -> None:
        if not self.agents:
            return

        async with self._lock():
            speaker_id = self._rng.choice(list(self.agents.keys()))
            spoken = await self.speak_once(speaker_id, prompt_kind="auto")
            if not spoken:
                return

            if self._rng.random() < self.followup_probability:
                responders = self._choose_other_agents(speaker_id, min_count=1, max_count=2)
                for responder_id in responders:
                    await self.speak_once(responder_id, prompt_kind="followup", trigger_message=spoken)

    async def handle_user_interjection(self, content: str, anchor_agent_id: str | None = None) -> None:
        content = content.strip()
        if not content:
            return

        async with self._lock():
            user_message = BusMessage(
                sender="你",
                content=content,
                kind="user",
                anchor_agent_id=anchor_agent_id,
            )
            self.broadcast(user_message)

            responders = self._choose_user_responders(anchor_agent_id)
            for responder_id in responders:
                await self.speak_once(responder_id, prompt_kind="user", trigger_message=user_message)

    async def speak_once(
        self,
        agent_id: str,
        prompt_kind: str = "auto",
        trigger_message: BusMessage | None = None,
    ) -> BusMessage | None:
        agent = self.agents.get(agent_id)
        if agent is None:
            return None

        history = self._build_history_messages()
        prompt = self._build_prompt(agent, prompt_kind, trigger_message)
        tool_context = ToolContext(
            agent_id=agent_id,
            agent_name=agent.name,
            sandbox=default_sandbox(),
            permission_requester=self.permission_requester,
            screenshot_requester=self.screenshot_requester,
            tool_event_callback=self._on_tool_event,
        )
        try:
            reply = await agent.chat(prompt, history=history, tool_context=tool_context)
        except Exception:
            reply = "我刚刚卡住了，请稍后再试。"

        reply = reply.strip()
        if not reply:
            return None

        message = BusMessage(
            sender=agent.name,
            content=reply,
            kind="agent",
            agent_id=agent_id,
            anchor_agent_id=agent_id,
        )
        self.broadcast(message)
        return message

    def _on_tool_event(self, event: str, request: ToolCallRequest, payload: dict | None) -> None:
        labels = {
            "permission_requested": "请求使用工具",
            "permission_denied": "已拒绝工具",
            "started": "开始执行工具",
            "finished": "已完成工具",
            "failed": "工具执行失败",
        }
        label = labels.get(event)
        if not label:
            return
        self.broadcast(BusMessage(
            sender="系统",
            content=f"{request.agent_name} {label}：{request.tool_name}",
            kind="tool",
            agent_id=request.agent_id,
            anchor_agent_id=request.agent_id,
        ))

    def _lock(self) -> asyncio.Lock:
        if self._conversation_lock is None:
            self._conversation_lock = asyncio.Lock()
        return self._conversation_lock

    def _choose_other_agents(self, speaker_id: str, min_count: int, max_count: int) -> list[str]:
        candidates = [agent_id for agent_id in self.agents if agent_id != speaker_id]
        if not candidates:
            return []
        count = self._rng.randint(min_count, min(max_count, len(candidates)))
        return self._rng.sample(candidates, count)

    def _choose_user_responders(self, anchor_agent_id: str | None) -> list[str]:
        if not self.agents:
            return []

        responders: list[str] = []
        if anchor_agent_id in self.agents:
            responders.append(anchor_agent_id)

        candidates = [agent_id for agent_id in self.agents if agent_id not in responders]
        total_count = self._rng.randint(1, min(2, len(self.agents)))
        needed = max(0, total_count - len(responders))
        if needed and candidates:
            responders.extend(self._rng.sample(candidates, min(needed, len(candidates))))
        return responders

    def _build_history_messages(self) -> list[dict[str, str]]:
        if not self.recent_history:
            return []

        transcript = ["以下是最近的群聊记录："]
        for msg in self.recent_history:
            speaker = "用户" if msg.kind == "user" else msg.sender
            transcript.append(f"{speaker}: {msg.content}")
        return [{"role": "user", "content": "\n".join(transcript)}]

    def _build_prompt(self, agent: Agent, prompt_kind: str, trigger_message: BusMessage | None) -> str:
        base_rules = (
            f"请作为 {agent.name} 在这个桌面小组聊天中自然发言。\n"
            "要求：\n"
            "- 只输出你的发言内容，不要加姓名前缀\n"
            "- 1到2句话\n"
            "- 中文\n"
            "- 符合你的人设和表达风格"
        )

        if prompt_kind == "user" and trigger_message:
            return f"用户刚刚插话：{trigger_message.content}\n\n{base_rules}\n请自然回应用户，也可以顺带接住群聊上下文。"
        if prompt_kind == "followup" and trigger_message:
            return f"{trigger_message.sender} 刚刚说：{trigger_message.content}\n\n{base_rules}\n请自然接话或补充观点。"
        return f"{base_rules}\n如果最近没有明确话题，就主动开启一个轻松、有用的话题。"
