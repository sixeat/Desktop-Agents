# Desktop Agents 开发文档

> 日期：2026-05-23

本文档记录当前实现状态和维护视角。当前代码已从“带工具执行的桌面 Agent”收缩为“轻量桌面多 Agent 聊天应用”。

## 1. 当前开发目标

当前目标是收敛 1.0 范围：

1. 保留多 Agent 桌面聊天。
2. 保留人格配置、人格切换和聊天记录。
3. 保留 API Key / OpenAI-compatible 基础配置。
4. 删除工具执行、权限分级、截图等过度设计能力。
5. 暂不推送精简版，等用户确认 1.0 后再推送。

## 2. 当前核心调用链

主流程：

```text
main.py
  -> ensure_llm_configured()
  -> load_llm_settings()
  -> OpenAICompatibleClient
  -> Agent
  -> AgentBus
  -> AgentManager
  -> AgentWidget
```

聊天流程：

```text
AgentBus.speak_once()
  -> Agent.chat()
  -> OpenAICompatibleClient.chat()
  -> OpenAICompatibleClient.complete()
  -> 返回纯文本
```

当前 `Agent` 不再持有工具注册表，也不再处理 `tool_calls`。

## 3. 已移除的工具执行能力

已删除文件：

- `core/tooling.py`
- `core/builtin_tools.py`
- `ui/tool_permission_dialog.py`
- `tests/test_tool_executor.py`
- `tests/test_agent_tools.py`
- `tests/test_llm_client_tools.py`

已移除概念：

- `PermissionLevel`
- `ToolDefinition`
- `ToolCallRequest`
- `ToolResult`
- `ToolContext`
- `SandboxPolicy`
- `ToolRegistry`
- `ToolExecutor`
- `read_file`
- `execute_command`
- `screenshot`

已清理接线：

- `main.py` 不再创建 `ToolRegistry.with_defaults()`。
- `AgentBus` 不再保存 `permission_requester` / `screenshot_requester`。
- `AgentBus.speak_once()` 不再构造 `ToolContext`。
- `AgentManager` 不再桥接工具权限弹窗和截图请求。
- `OpenAICompatibleClient.complete()` 不再接收 `tools` / `tool_choice`。

## 4. 保留的 API Key 与模型配置

### `core/llm_settings.py`

负责运行时 LLM 配置读取与保存：

- `LLMSettings`
- `load_llm_settings()`
- `has_api_key()`
- `save_llm_settings(...)`
- `settings_to_client_kwargs(...)`

配置优先级：

1. 环境变量 / `.env`
2. `keyring`
3. `QSettings`
4. 默认值

保存策略：

- Provider / Base URL / Model 保存到 `QSettings`。
- API Key 优先保存到系统凭据管理器 `keyring`。
- 如果 `keyring` 不可用，fallback 保存到当前 Windows 用户级 `QSettings`。
- 不写入项目 `.env`。

### `ui/api_key_dialog.py`

用于首次配置和随时修改 API Key。

字段：

- Provider
- Base URL
- Model
- API Key

右键菜单中保留：

```text
API Key 设置
```

托盘菜单不再放 API Key 设置入口。

## 5. UI 当前状态

### `ui/agent_widget.py`

保留：

- 桌面头像
- 点击输入消息
- 右键切换人格
- 右键聊天记录
- 右键导入聊天记录人格
- 右键 API Key 设置
- 右键退出
- 简化系统托盘

托盘菜单只保留：

- 显示
- 隐藏
- 退出

### `ui/agent_manager.py`

保留：

- AgentWidget 创建和定位
- 群聊消息展示
- 聊天记录窗口
- API Key 设置热更新
- 聊天记录人格导入
- 人格刷新和切换

已移除：

- 工具权限请求桥接
- 截图请求桥接
- 工具状态消息广播

## 6. 聊天记录导入流程

导入入口仍然在 Agent 右键菜单：

```text
导入聊天记录人格
```

导入弹窗以本地文件为主：

```text
导入聊天记录文件
批量导入
```

支持格式：

- `txt`
- `csv`
- `json`
- `sqlite`
- `db`
- `sqlite3`

wx-mcp 只作为参考链接展示，不在项目内自动下载和安装。

## 7. 测试

当前保留核心测试：

- `tests/test_agent_conversation.py`
- `tests/test_agent_bus.py`
- `tests/test_personality.py`

当前验证结果：

```text
py -3.14 -m unittest desktop-agents.tests.test_agent_conversation desktop-agents.tests.test_agent_bus desktop-agents.tests.test_personality
Ran 12 tests
OK
```

工具相关测试已随工具框架一起删除。

## 8. 当前修改文件总览

### 删除

- `core/tooling.py`
- `core/builtin_tools.py`
- `ui/tool_permission_dialog.py`
- `tests/test_agent_tools.py`
- `tests/test_tool_executor.py`
- `tests/test_llm_client_tools.py`

### 重点修改

- `main.py`
- `core/agent.py`
- `core/agent_bus.py`
- `core/llm_client.py`
- `ui/agent_manager.py`
- `ui/agent_widget.py`
- `AGENT_WORK_GUIDE.md`
- `PROGRESS.md`
- `DEVELOPMENT_LOG.md`

## 9. 当前已知限制

1. 多模型目前是 OpenAI-compatible 基础配置，没有完整 Provider 预设 UI。
2. API Key fallback 到 QSettings 是为了解决本机 keyring 不可用问题，安全性弱于系统凭据管理器。
3. 自动群聊没有暂停/频率 UI。
4. 聊天记录人格导入仍然是较大的功能块，后续可继续评估是否保留。
5. 当前版本不具备读文件、执行命令、截图能力。

## 10. 下次开发建议

优先级建议：

1. 继续确认 1.0 范围。
2. 评估是否保留聊天记录导入人格。
3. 评估是否保留聊天记录窗口。
4. 简化右键菜单和默认 Agent 数量。
5. 手动完整验证启动、聊天、切换人格、API Key 设置。
6. 用户确认 1.0 后再提交、打标签、推送。
