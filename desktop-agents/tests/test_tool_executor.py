import tempfile
import unittest
from pathlib import Path

from core.builtin_tools import execute_command_tool, read_file_tool
from core.tooling import PermissionLevel, SandboxPolicy, ToolContext, ToolDefinition, ToolExecutor, ToolRegistry


class ToolExecutorTest(unittest.IsolatedAsyncioTestCase):
    def test_registry_exports_schema_and_rejects_duplicates(self):
        tool = ToolDefinition(
            name="hello",
            description="hello tool",
            parameters={"type": "object"},
            permission_level=PermissionLevel.SAFE,
            handler=lambda args, ctx: {"hello": "world"},
        )
        registry = ToolRegistry([tool])

        schema = registry.to_deepseek_tools()[0]

        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "hello")
        with self.assertRaises(ValueError):
            registry.register(tool)

    async def test_safe_tool_runs_without_permission(self):
        called = []
        tool = ToolDefinition(
            name="safe_tool",
            description="safe",
            parameters={"type": "object"},
            permission_level=PermissionLevel.SAFE,
            handler=lambda args, ctx: called.append(args) or {"ok_value": 1},
        )
        registry = ToolRegistry([tool])
        context = ToolContext("agent", "Agent", SandboxPolicy((Path.cwd(),)))

        result = await ToolExecutor(registry).execute("safe_tool", '{"x": 1}', context)

        self.assertTrue(result.ok)
        self.assertEqual(called, [{"x": 1}])

    async def test_normal_tool_denied_does_not_run_handler(self):
        called = []
        tool = ToolDefinition(
            name="normal_tool",
            description="normal",
            parameters={"type": "object"},
            permission_level=PermissionLevel.NORMAL,
            handler=lambda args, ctx: called.append(args) or {},
        )
        registry = ToolRegistry([tool])
        context = ToolContext(
            "agent",
            "Agent",
            SandboxPolicy((Path.cwd(),)),
            permission_requester=lambda request: False,
        )

        result = await ToolExecutor(registry).execute("normal_tool", "{}", context)

        self.assertFalse(result.ok)
        self.assertEqual(called, [])
        self.assertIn("拒绝", result.error)

    async def test_read_file_allows_project_text_and_rejects_outside_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            allowed = root / "note.txt"
            allowed.write_text("hello", encoding="utf-8")
            outside = root.parent / "outside_tool_test.txt"
            outside.write_text("secret", encoding="utf-8")
            self.addCleanup(lambda: outside.unlink(missing_ok=True))
            context = ToolContext(
                "agent",
                "Agent",
                SandboxPolicy((root,)),
                permission_requester=lambda request: True,
            )
            registry = ToolRegistry([read_file_tool()])
            executor = ToolExecutor(registry)

            ok = await executor.execute("read_file", {"path": str(allowed)}, context)
            blocked = await executor.execute("read_file", {"path": str(outside)}, context)

        self.assertTrue(ok.ok)
        self.assertEqual(ok.content["content"], "hello")
        self.assertFalse(blocked.ok)

    async def test_execute_command_requires_permission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = ToolContext(
                "agent",
                "Agent",
                SandboxPolicy((Path(temp_dir),)),
                permission_requester=lambda request: False,
            )
            registry = ToolRegistry([execute_command_tool()])

            result = await ToolExecutor(registry).execute(
                "execute_command",
                {"program": "py", "args": ["--version"], "cwd": temp_dir},
                context,
            )

        self.assertFalse(result.ok)
        self.assertIn("拒绝", result.error)


if __name__ == "__main__":
    unittest.main()
