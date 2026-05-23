import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT
from core.tooling import PermissionLevel, SandboxPolicy, ToolCallRequest, ToolContext, ToolDefinition

SENSITIVE_NAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials",
    "config.json",
}

SENSITIVE_SUFFIXES = {".pem", ".key", ".pfx", ".p12"}


def default_sandbox() -> SandboxPolicy:
    return SandboxPolicy(allowed_roots=(PROJECT_ROOT.resolve(),))


def default_tools(sandbox: SandboxPolicy | None = None) -> list[ToolDefinition]:
    return [
        read_file_tool(),
        execute_command_tool(),
        screenshot_tool(),
    ]


def read_file_tool() -> ToolDefinition:
    return ToolDefinition(
        name="read_file",
        description="读取项目允许目录内的文本文件内容。",
        permission_level=PermissionLevel.NORMAL,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要读取的文件路径。"},
                "reason": {"type": "string", "description": "读取该文件的原因。"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=read_file_handler,
    )


def execute_command_tool() -> ToolDefinition:
    return ToolDefinition(
        name="execute_command",
        description="在受限目录内执行非交互式本地命令。高风险操作，每次都需要用户确认。",
        permission_level=PermissionLevel.DANGEROUS,
        parameters={
            "type": "object",
            "properties": {
                "program": {"type": "string", "description": "要执行的程序名或可执行文件路径。"},
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "命令参数数组，不接受 shell 字符串。",
                },
                "cwd": {"type": "string", "description": "工作目录，必须在允许目录内。"},
                "reason": {"type": "string", "description": "执行该命令的原因。"},
            },
            "required": ["program"],
            "additionalProperties": False,
        },
        handler=execute_command_handler,
    )


def screenshot_tool() -> ToolDefinition:
    return ToolDefinition(
        name="screenshot",
        description="截取当前主屏幕并返回本地截图文件路径和尺寸元数据。",
        permission_level=PermissionLevel.NORMAL,
        parameters={
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "截图原因。"},
            },
            "additionalProperties": False,
        },
        handler=screenshot_handler,
    )


def read_file_handler(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    raw_path = str(arguments.get("path") or "").strip()
    if not raw_path:
        raise ValueError("缺少 path。")

    path = Path(raw_path).expanduser().resolve()
    if not context.sandbox.is_path_allowed(path):
        raise ValueError("文件不在允许读取的目录内。")
    if path.name.lower() in SENSITIVE_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES:
        raise ValueError("出于安全原因拒绝读取敏感文件。")
    if not path.exists():
        raise ValueError("文件不存在。")
    if path.is_dir():
        raise ValueError("不能读取目录。")

    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        raise ValueError("拒绝读取疑似二进制文件。")

    truncated = len(data) > context.sandbox.max_file_bytes
    data = data[: context.sandbox.max_file_bytes]
    text = data.decode("utf-8", errors="replace")
    return {
        "path": str(path),
        "content": text,
        "bytes_read": len(data),
        "truncated": truncated,
    }


async def execute_command_handler(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    program = str(arguments.get("program") or "").strip()
    if not program:
        raise ValueError("缺少 program。")
    if any(token in program for token in ["&", "|", ";", "<", ">"]):
        raise ValueError("program 必须是单个程序，不能包含 shell 操作符。")

    raw_args = arguments.get("args") or []
    if not isinstance(raw_args, list) or not all(isinstance(item, str) for item in raw_args):
        raise ValueError("args 必须是字符串数组。")

    cwd = Path(str(arguments.get("cwd") or PROJECT_ROOT)).expanduser().resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise ValueError("cwd 不存在或不是目录。")
    if not context.sandbox.is_path_allowed(cwd):
        raise ValueError("cwd 不在允许目录内。")

    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "TEMP": tempfile.gettempdir(),
        "TMP": tempfile.gettempdir(),
    }

    process = await asyncio.create_subprocess_exec(
        program,
        *raw_args,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=context.sandbox.command_timeout_seconds,
        )
    except asyncio.TimeoutError:
        timed_out = True
        process.kill()
        stdout, stderr = await process.communicate()

    max_bytes = context.sandbox.max_output_bytes
    stdout_truncated = len(stdout) > max_bytes
    stderr_truncated = len(stderr) > max_bytes
    return {
        "program": program,
        "args": raw_args,
        "cwd": str(cwd),
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "stdout": stdout[:max_bytes].decode("utf-8", errors="replace"),
        "stderr": stderr[:max_bytes].decode("utf-8", errors="replace"),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }


async def screenshot_handler(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    if context.screenshot_requester is None:
        raise ValueError("当前没有可用的截图服务。")
    request = ToolCallRequest(
        agent_id=context.agent_id,
        agent_name=context.agent_name,
        tool_name="screenshot",
        arguments=arguments,
        permission_level=PermissionLevel.NORMAL,
    )
    result = context.screenshot_requester(request)
    if hasattr(result, "__await__"):
        result = await result
    return dict(result)
