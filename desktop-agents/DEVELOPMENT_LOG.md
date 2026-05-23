# Desktop Agents 开发文档

> 日期：2026-05-23

本文档记录今天的技术开发内容，偏实现细节和后续维护视角。它和 `AGENT_WORK_GUIDE.md` 的区别是：

- `AGENT_WORK_GUIDE.md`：给使用者看，说明怎么让 Agent 干活。
- `DEVELOPMENT_LOG.md`：给开发者看，记录今天改了哪些模块、为什么这么改、后续怎么接着开发。

## 1. 今日开发目标

今天主要围绕三个方向推进：

1. 让聊天记录人格导入更稳定、更安全。
2. 给 Agent 增加工具执行能力。
3. 增加启动配置和 API Key 管理，让用户不需要手动改环境变量。

## 2. 聊天记录导入流程调整

### 背景

之前探索过 wx-mcp 和 MemoTrace/WeChatMsg 方案。MemoTrace 因版本限制不再作为主要方案。wx-mcp 保留为用户自行参考的导出方案，但项目内不再自动下载和安装。

### 当前设计

导入入口仍然在 Agent 右键菜单：

```text
导入聊天记录人格
```

导入弹窗现在以本地文件为主：

```text
导入聊天记录文件
批量导入
```

### 支持格式

当前支持：

- `txt`
- `csv`
- `json`
- `sqlite`
- `db`
- `sqlite3`

### 关键文件

- `ui/import_dialog.py`
- `core/importer/wechat_importer.py`
- `tools/wechat/parsers.py`
- `core/importer/wx_mcp_client.py`

### 关键变更

- 移除了应用内“一键安装 wx-mcp”的流程。
- 移除了 UI 上的“刷新 wx-mcp 状态”按钮。
- 文案改成推荐用户选择本地聊天记录文件或文件夹。
- wx-mcp 只作为参考链接：

```text
https://github.com/r266-tech/wechat-local-mcp
```

### 原因

这样可以减少：

- 下载失败问题。
- 第三方工具信任问题。
- 自动安装带来的安全和维护成本。

## 3. Agent 工具执行能力

### 背景

原本 Agent 只能聊天，调用链大致是：

```text
AgentBus.speak_once()
  -> Agent.chat()
  -> OpenAICompatibleClient.chat()
  -> 返回纯文本
```

今天改为支持 Function Calling / tool_calls，让 Agent 可以调用工具。

### 新增核心文件

#### `core/tooling.py`

新增工具运行时基础设施：

- `PermissionLevel`
  - `SAFE`
  - `NORMAL`
  - `DANGEROUS`
- `ToolDefinition`
- `ToolCallRequest`
- `ToolResult`
- `ToolContext`
- `SandboxPolicy`
- `ToolRegistry`
- `ToolExecutor`

设计重点：

- 每个 Agent 拥有自己的 `ToolRegistry`。
- 工具执行返回结构化结果。
- 权限检查在 handler 执行前完成。
- handler 异常不会直接向外抛，而是转成模型可见的工具错误。

#### `core/builtin_tools.py`

新增内置工具：

##### `read_file`

权限：`NORMAL`

能力：读取项目允许目录内的文本文件。

限制：

- 默认只允许项目目录。
- 拒绝目录。
- 拒绝疑似二进制文件。
- 拒绝 `.env`、私钥、证书等敏感文件。
- 限制读取字节数。

##### `execute_command`

权限：`DANGEROUS`

能力：执行本地命令。

限制：

- 不接受 shell 字符串。
- 使用结构化参数：`program` + `args`。
- 不使用 `shell=True`。
- 限制工作目录。
- 限制执行超时。
- 限制 stdout/stderr 输出大小。
- 使用精简环境变量。

##### `screenshot`

权限：`NORMAL`

能力：通过 GUI 线程截图。

当前状态：

- 返回截图路径和尺寸信息。
- 还没有接入视觉模型或 OCR。

### 修改 Agent 调用链

#### `core/llm_client.py`

新增/调整：

- `OpenAICompatibleClient`
- `complete(...)`
  - 返回完整 assistant message。
  - 支持传入 `tools` 和 `tool_choice`。
- `chat(...)`
  - 保留纯文本兼容。
- `DeepSeekClient = OpenAICompatibleClient`
  - 保留旧名称兼容。

#### `core/agent.py`

新增：

- `tools: ToolRegistry`
- `tool_executor: ToolExecutor`
- `_chat_with_tools(...)`

工具调用循环：

1. 把 tools schema 发给模型。
2. 如果模型返回普通文本，直接返回。
3. 如果模型返回 `tool_calls`：
   - 解析工具名和参数。
   - 通过 `ToolExecutor` 执行。
   - 把工具结果作为 `role="tool"` 消息追加。
   - 再次请求模型生成最终回答。
4. 最多循环 4 次，防止无限调用工具。

历史记录策略：

- 没有外部 history 时，只保存用户输入和最终 assistant 回复。
- 不把原始工具输出长期写入 Agent history。

#### `core/agent_bus.py`

新增：

- `permission_requester`
- `screenshot_requester`
- 工具事件广播 `_on_tool_event(...)`

`AgentBus.speak_once()` 会构造 `ToolContext` 传给 Agent。

工具事件只广播简短状态，例如：

```text
小明 请求使用工具：read_file
小明 已完成工具：read_file
```

不会把文件内容或命令输出广播到群聊记录。

## 4. 工具权限 UI

### 新增文件

#### `ui/tool_permission_dialog.py`

用于显示工具执行确认。

显示内容：

- Agent 名称
- 工具名称
- 权限等级
- 工具参数 JSON

按钮：

- `允许一次`
- `拒绝`

`DANGEROUS` 权限会使用更强的红色警告样式。

### 修改文件

#### `ui/agent_manager.py`

新增 GUI 线程桥接：

- `tool_permission_requested`
- `screenshot_requested`
- `request_tool_permission(...)`
- `request_screenshot(...)`
- `_show_tool_permission_dialog(...)`
- `_capture_screenshot(...)`

原因：

工具调用发生在 AgentBus 的后台异步流程中，不能直接在后台线程创建 Qt 对话框，所以通过 Qt signal 桥到 GUI 线程。

## 5. 多模型基础配置

### 背景

用户提出希望像 openclaw 一样支持多种大模型。

### 今日实现范围

今天完成的是 OpenAI-compatible 基础抽象，不是完整模型市场/多 Provider UI。

### 配置项

支持环境变量：

```text
LLM_PROVIDER
LLM_API_KEY
LLM_BASE_URL
LLM_MODEL
```

兼容旧变量：

```text
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL
DEEPSEEK_MODEL
```

### 关键文件

- `config.py`
- `core/llm_client.py`

## 6. API Key 启动检测与管理

### 新增文件

#### `core/llm_settings.py`

负责运行时 LLM 配置读取与保存。

核心结构：

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

#### `ui/api_key_dialog.py`

用于首次配置和随时修改 API Key。

字段：

- Provider
- Base URL
- Model
- API Key

特点：

- API Key 输入框默认密码模式。
- 已有 Key 只显示遮罩 placeholder。
- 首次使用时 Key 不能为空。
- 保存后不显示明文 Key。

### 修改启动流程

#### `main.py`

原流程：

```text
QApplication
创建 Agents
创建 AgentBus
创建 AgentManager
启动
```

新流程：

```text
QApplication
ensure_llm_configured()
  如果没有 Key -> 弹出首次配置
  如果取消 -> 退出
加载 LLMSettings
创建 OpenAICompatibleClient
创建 Agents
创建 AgentBus
创建 AgentManager
启动
```

### 随时修改入口

#### `ui/agent_widget.py`

新增信号：

```python
api_key_settings_requested = pyqtSignal()
```

右键菜单新增：

```text
API Key 设置
```

托盘菜单新增：

```text
API Key 设置
```

#### `ui/agent_manager.py`

新增方法：

```python
show_api_key_settings()
```

保存后：

- 重新加载 LLMSettings。
- 给每个 Agent 替换新的 `OpenAICompatibleClient`。
- 广播系统消息：

```text
API Key 设置已更新。
```

## 7. 测试

### 新增测试文件

- `tests/test_tool_executor.py`
- `tests/test_agent_tools.py`
- `tests/test_llm_client_tools.py`
- `tests/test_llm_settings.py`
- `tests/test_api_key_dialog.py`

### 覆盖点

工具相关：

- 工具注册表导出 schema。
- 重复工具名拒绝。
- SAFE 工具无需权限。
- NORMAL / DANGEROUS 工具需要权限。
- 拒绝权限后 handler 不执行。
- 读文件工具限制目录。
- Agent 能执行 tool_call 并把结果发回模型。
- 未知工具会返回模型可见错误。
- 每个 Agent 工具集独立。

模型相关：

- `complete()` 能发送 tools 和 tool_choice。
- 显式构造参数优先。
- 缺 Key 消息指向 API Key 设置。
- 客户端可运行时加载配置。

Key 管理相关：

- 从 `LLM_API_KEY` 加载。
- 从 `DEEPSEEK_API_KEY` fallback 加载。
- QSettings + keyring 保存和读取。
- keyring 不可用时 fallback 到 QSettings。
- Dialog 默认密码输入。
- 已有 Key 不显示明文。
- 输入值会 trim。

### 今日最终测试结果

```text
py -m compileall F:\xmlg\agent\desktop-agents
OK

py -m unittest discover -s F:\xmlg\agent\desktop-agents\tests
Ran 45 tests
OK
```

## 8. 今日新增/修改文件总览

### 新增

- `AGENT_WORK_GUIDE.md`
- `PROGRESS.md`
- `DEVELOPMENT_LOG.md`
- `core/tooling.py`
- `core/builtin_tools.py`
- `core/llm_settings.py`
- `ui/tool_permission_dialog.py`
- `ui/api_key_dialog.py`
- `tests/test_tool_executor.py`
- `tests/test_agent_tools.py`
- `tests/test_llm_client_tools.py`
- `tests/test_llm_settings.py`
- `tests/test_api_key_dialog.py`

### 重点修改

- `main.py`
- `config.py`
- `core/agent.py`
- `core/agent_bus.py`
- `core/llm_client.py`
- `ui/agent_manager.py`
- `ui/agent_widget.py`
- `ui/import_dialog.py`
- `core/importer/wechat_importer.py`
- `core/importer/wx_mcp_client.py`
- `requirements.txt`

## 9. 当前已知限制

1. `execute_command` 是应用层限制，不是系统级强沙箱。
2. 截图工具目前只返回截图文件信息，模型还不能直接看图。
3. 多模型目前是 OpenAI-compatible 基础配置，没有完整 Provider 预设 UI。
4. API Key fallback 到 QSettings 是为了解决本机 keyring 不可用问题，安全性弱于系统凭据管理器。
5. 工具调用还没有 per-Agent 图形化开关。
6. 长期任务队列还未实现。

## 10. 下次开发建议

优先级建议：

1. 增加任务队列，让 Agent 可以持续执行任务。
2. 增加 Provider 预设和测试连接按钮。
3. 增加 per-Agent 工具开关。
4. 增加文件搜索 / 项目结构分析工具。
5. 接入视觉模型或 OCR，让 screenshot 工具真正可被模型理解。
6. 加强命令执行安全策略，例如 allowlist、二次确认、执行日志。
