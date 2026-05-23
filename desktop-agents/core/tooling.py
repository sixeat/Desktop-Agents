import asyncio
import inspect
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable


class PermissionLevel(str, Enum):
    SAFE = "safe"
    NORMAL = "normal"
    DANGEROUS = "dangerous"


ToolHandler = Callable[[dict[str, Any], "ToolContext"], dict[str, Any] | Awaitable[dict[str, Any]]]
PermissionRequester = Callable[["ToolCallRequest"], bool | Awaitable[bool]]
ScreenshotRequester = Callable[["ToolCallRequest"], dict[str, Any] | Awaitable[dict[str, Any]]]
ToolEventCallback = Callable[[str, "ToolCallRequest", dict[str, Any] | None], None]


@dataclass(frozen=True)
class SandboxPolicy:
    allowed_roots: tuple[Path, ...]
    max_file_bytes: int = 64 * 1024
    max_output_bytes: int = 16 * 1024
    command_timeout_seconds: float = 10.0

    def is_path_allowed(self, path: Path) -> bool:
        resolved = path.resolve()
        for root in self.allowed_roots:
            try:
                resolved.relative_to(root.resolve())
                return True
            except ValueError:
                continue
        return False


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    permission_level: PermissionLevel
    handler: ToolHandler

    def to_deepseek_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCallRequest:
    agent_id: str
    agent_name: str
    tool_name: str
    arguments: dict[str, Any]
    permission_level: PermissionLevel
    tool_call_id: str | None = None


@dataclass
class ToolResult:
    ok: bool
    content: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_message_content(self) -> str:
        data: dict[str, Any] = {"ok": self.ok}
        if self.content:
            data.update(self.content)
        if self.error:
            data["error"] = self.error
        return json.dumps(data, ensure_ascii=False)


@dataclass
class ToolContext:
    agent_id: str
    agent_name: str
    sandbox: SandboxPolicy
    permission_requester: PermissionRequester | None = None
    screenshot_requester: ScreenshotRequester | None = None
    tool_event_callback: ToolEventCallback | None = None

    def emit_event(self, event: str, request: ToolCallRequest, payload: dict[str, Any] | None = None) -> None:
        if self.tool_event_callback:
            self.tool_event_callback(event, request, payload)


class ToolRegistry:
    def __init__(self, tools: list[ToolDefinition] | None = None):
        self._tools: dict[str, ToolDefinition] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"重复的工具名称：{tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def __bool__(self) -> bool:
        return bool(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def to_deepseek_tools(self) -> list[dict[str, Any]]:
        return [tool.to_deepseek_tool() for tool in self._tools.values()]

    @classmethod
    def with_defaults(cls, sandbox: SandboxPolicy | None = None) -> "ToolRegistry":
        from core.builtin_tools import default_tools

        return cls(default_tools(sandbox=sandbox))


class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(
        self,
        tool_name: str,
        raw_arguments: str | dict[str, Any] | None,
        context: ToolContext,
        tool_call_id: str | None = None,
    ) -> ToolResult:
        tool = self.registry.get(tool_name)
        if tool is None:
            return ToolResult(ok=False, error=f"未知工具：{tool_name}")

        try:
            arguments = self._parse_arguments(raw_arguments)
        except ValueError as exc:
            return ToolResult(ok=False, error=str(exc))

        request = ToolCallRequest(
            agent_id=context.agent_id,
            agent_name=context.agent_name,
            tool_name=tool.name,
            arguments=arguments,
            permission_level=tool.permission_level,
            tool_call_id=tool_call_id,
        )

        if tool.permission_level != PermissionLevel.SAFE:
            context.emit_event("permission_requested", request, None)
            allowed = await self._request_permission(context, request)
            if not allowed:
                context.emit_event("permission_denied", request, None)
                return ToolResult(ok=False, error="用户拒绝了工具执行。")

        context.emit_event("started", request, None)
        try:
            value = tool.handler(arguments, context)
            if inspect.isawaitable(value):
                value = await value
            if not isinstance(value, dict):
                value = {"result": value}
            context.emit_event("finished", request, value)
            return ToolResult(ok=True, content=value)
        except Exception as exc:
            error = f"工具执行失败：{exc}"
            context.emit_event("failed", request, {"error": error})
            return ToolResult(ok=False, error=error)

    def _parse_arguments(self, raw_arguments: str | dict[str, Any] | None) -> dict[str, Any]:
        if raw_arguments is None or raw_arguments == "":
            return {}
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not isinstance(raw_arguments, str):
            raise ValueError("工具参数格式无效。")
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            raise ValueError("工具参数不是合法 JSON。")
        if not isinstance(parsed, dict):
            raise ValueError("工具参数必须是 JSON 对象。")
        return parsed

    async def _request_permission(self, context: ToolContext, request: ToolCallRequest) -> bool:
        if context.permission_requester is None:
            return False
        result = context.permission_requester(request)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)
