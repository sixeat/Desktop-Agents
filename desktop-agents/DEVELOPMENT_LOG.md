# Desktop Agents 开发文档

> 日期：2026-05-24

本文档记录当前实现状态和维护视角。当前代码已从“带工具执行的桌面 Agent”收缩为“轻量桌面多 Agent 聊天应用”。项目核心目标是从用户和朋友的聊天记录中蒸馏出“我”或“朋友”的人格 Agent，并用桌面宠物/头像形象承载这些人格。

## 1. 当前开发目标

当前目标是围绕轻量桌面多 Agent 聊天应用收敛 1.0 范围：

1. 以“聊天记录 → 人格 Agent → 桌面形象承载”为产品主线。
2. 默认启动桌面人格 Agent 模式，当前支持持久化单 Agent 管理和自定义情绪 PNG 形象。
3. 保留桌面 Agent 的拖动、点击、情绪、气泡交互，并支持正常/开心/难过/困/惊讶/生气 6 张 PNG 随情绪切换。
4. 保留人格训练、默认人格和人格 × 情绪联动。
5. 保留单 Agent 聊天窗口和多 Agent 自动群聊。
6. 保留群聊记录和单 Agent 记录，并各自只保留最近 50 条。
7. 支持默认桌面 Agent 从 `.json/.txt/.csv` 聊天导出文件导入人格。
8. 保留 API Key / OpenAI-compatible 基础配置。
9. 后续支持自定义宠物/头像形象。
10. 保留旧版 `--mode agents` 作为兼容模式。
11. 删除工具执行、权限分级、截图等过度设计能力。
12. 暂不推送，等用户确认 1.0 后再提交、打标签、推送。

## 2. 当前核心调用链

### 默认桌面人格 Agent 模式

```text
main.py
  -> run_pet_mode()
  -> pet_registry.load_pet_configs()
  -> AgentEditDialog（首次无 Agent 时）
  -> PetManager
  -> PetWidget
  -> PetCompanion
  -> EmotionEngine
  -> PersonalityProfile / PersonalityTrainer
  -> OpenAICompatibleClient（仅配置 API Key 后）
```

单 Agent 聊天流程：

```text
PetWidget 双击
  -> PetWidget.chat_window_requested
  -> PetManager.show_pet_chat_window()
  -> PetChatWindow.message_submitted
  -> PetManager._on_pet_chat_requested()
  -> 记录用户消息到 direct_histories[widget]
  -> 无 API Key: PetCompanion.handle_interaction("chat", text)
  -> 有 API Key: PetManager._chat_with_llm(..., channel="direct")
  -> PetCompanion.chat()
  -> PetManager._show_chat_response(..., "direct")
  -> 更新 mood / 气泡 / 单 Agent 记录 / 可见聊天窗口
```

右键 `和它说话` 仍保留为单条输入弹窗备用入口，后续同样进入 `PetManager._on_pet_chat_requested()`。

默认模式人格导入流程：

```text
PetWidget 右键“导入人格”
  -> PetWidget.persona_import_requested
  -> PetManager.import_persona_for_pet()
  -> PetPersonaImportDialog
  -> pet_persona_importer.load_profile_from_export()
  -> tools.wechat.parsers.load_export_dir()
  -> PersonalityTrainer.analyze()
  -> pet_persona_importer.save_pet_persona()
  -> PetCompanion.apply_profile()
  -> PetManager._show_chat_response(..., "direct")
```

自动群聊流程：

```text
PetManager.start_auto_chat()
  -> PetManager.run_auto_chat_once()
  -> 无 API Key: PetCompanion.handle_interaction("group_chat", prompt)
  -> 有 API Key: PetManager._chat_with_llm(..., channel="group")
  -> PetManager._show_chat_response(..., "group")
  -> 更新 mood / 气泡 / group_history
```

### 旧版头像 Agent 模式

```text
main.py
  -> run_agent_mode()
  -> ensure_llm_configured()
  -> load_llm_settings()
  -> OpenAICompatibleClient
  -> Agent
  -> AgentBus
  -> AgentManager
  -> AgentWidget
```

旧版群聊流程：

```text
AgentBus.speak_once()
  -> Agent.chat()
  -> OpenAICompatibleClient.chat()
  -> OpenAICompatibleClient.complete()
  -> BusMessage
  -> AgentManager / ChatHistoryWindow
```

当前 `Agent` 不再持有工具注册表，也不再处理 `tool_calls`。

## 3. 关键模块说明

### `core/pet.py`

负责桌面人格 Agent 的当前默认形象定义。这里的 pet 是现阶段的视觉载体，不代表产品目标是纯宠物应用：

- `PetMood`
- `PetDefinition`
- `PetConfig`
- 当前内置形象类型列表
- 默认性格映射
- 可选性格标签

### `core/personality_trainer.py`

负责从聊天文本生成“我”或“朋友”的人格档案，是项目主线“聊天记录蒸馏人格 Agent”的核心模块：

- `PersonalityProfile`
- `PersonalityTrainer.analyze()`
- 默认人格 `_default_profile()`
- System Prompt 构建
- JSON save/load
- 兼容现有 `core/personality.py` 的字典输出

依赖策略：`jieba` 是可选依赖；没有安装时使用正则 fallback，不阻塞默认应用启动。

### `core/pet_persona_importer.py`

默认桌面 Agent 人格导入适配层：

- 接收用户选择的 `.json` / `.txt` / `.csv` 文件或目录。
- 复用 `tools.wechat.parsers.load_export_dir()` 解析聊天导出。
- 优先使用目标联系人消息；目标消息太少时 fallback 到可读取的全部文本消息。
- 调用 `PersonalityTrainer.analyze()` 生成 `PersonalityProfile`。
- `save_pet_persona()` 将蒸馏后的人格档案保存为 `persona.json`。
- `safe_persona_slug()` 生成保存目录名。

维护约定：只保存人格档案和 prompt，不保存原始聊天文本。

### `core/emotion.py`

负责情绪识别和情绪提示：

- `EmotionSignal`
- `EmotionState`
- `EmotionEngine.analyze()`
- `mood_for_text()`
- `decay()`
- `mood_prompt()`

当前支持 normal / happy / sad / sleepy / angry / surprised，并按人格标签调整情绪倾向。

### `core/pet_companion.py`

桌面人格 Agent 的对话核心：

- 维护 `PetConfig`、人格档案、情绪引擎和当前情绪。
- `handle_interaction()` 处理本地点击、打招呼、群聊和无 Key 聊天。
- `chat()` 处理 LLM 聊天，有异常时 fallback 本地回复。
- `build_messages()` 将人格 prompt 和当前 mood 注入 LLM 上下文。
- `apply_profile()` 在人格导入后替换当前人格、清理旧上下文并重置情绪。
- `history` 只作为 LLM 上下文历史，受 `PET_CHAT_HISTORY_LIMIT` 控制。

维护约定：不要把 UI 详细聊天记录写入 `PetCompanion.history`。

### `core/pet_registry.py`

负责桌面人格 Agent 配置持久化：

- 保存和读取 `models/desktop_agents.json`。
- 为每个 Agent 补齐稳定 `agent_id`。
- 兼容旧配置的颜色 tuple/list 转换。
- 保存头像路径、人格路径和 6 情绪 PNG 路径。

### `ui/agent_edit_dialog.py`

单 Agent 新建/编辑弹窗：

- 设置 Agent 名称、基础类型和性格标签。
- 支持正常、开心、难过、困、惊讶、生气 6 张 PNG。
- 新建时可选择创建后立即导入人格。

### `ui/agent_management_dialog.py`

托盘 `Agent 管理` 窗口：

- 列出当前 Agent 的名称、类型、性格、形象和人格状态。
- 触发新建、编辑、删除、导入人格、更换形象和打开聊天。
- 实际状态变更由 `PetManager` 统一处理。

### `ui/pet_selector_dialog.py`

旧版固定 3 个桌面人格 Agent 选择器，当前保留为备用入口和兼容测试。

### `ui/pet_widget.py`

桌面人格 Agent 桌面表现层：

- 绘制当前默认圆形形象、表情和名字标签。
- 可加载 6 情绪 PNG 形象，路径来自 `PetConfig.mood_avatar_paths`。
- 加载头像时会把与图片边缘连通的近白色背景抠成透明，保留角色内部白色细节。
- 未配置或图片不可读时回退到默认彩色圆形。
- 呼吸动画。
- 情绪弹跳动画。
- 静态 PNG 情绪动作：开心摇摆、难过下沉、困倦轻晃、惊讶上跳、生气抖动。
- 鼠标拖动。
- 左键点击反馈。
- 双击打开单 Agent 聊天窗口。
- 桌面气泡展示。
- 右键菜单：打招呼、和它说话、聊天记录、导入人格、切换情绪、退出。

### `ui/pet_manager.py`

默认桌面人格 Agent 模式的主控制器：

- 创建和定位 `PetWidget`。
- 创建每个 `PetCompanion`。
- 动态新增、编辑、删除和保存单个 Agent。
- 管理系统托盘和 `Agent 管理` 窗口。
- 路由本地/LLM 聊天。
- 驱动自动群聊。
- 维护群聊记录和单 Agent 记录。
- 管理单 Agent 聊天窗口。
- 管理默认模式人格导入并只切换被选中的 Agent。
- 确保异步 LLM 回复按 `group` / `direct` 通道写入正确记录。

聊天记录状态：

- `group_history`：群聊最近 50 条。
- `direct_histories`：按 `PetWidget` 分开的单 Agent 最近 50 条。
- `group_history_window`：群聊记录窗口。
- `direct_history_windows`：每个 Agent 的单聊记录窗口。
- `direct_chat_windows`：每个 Agent 的独立输入式聊天窗口。

### `ui/pet_persona_import_dialog.py`

默认模式人格导入弹窗：

- 文件选择器限制 `.json` / `.txt` / `.csv`。
- `聊天记录里的联系人` 用于定位要分析的发言者。
- `导入后 Agent 名称` 用于生成 profile.name、桌面显示名和聊天窗口标题。
- 点击 `分析` 后显示人格预览。
- 点击 `确认导入` 后把 `PersonalityProfile` 交回 `PetManager` 保存并应用。

当前同步分析文件；如果后续遇到大文件卡顿，再迁移到 `QThread`。

### `ui/pet_chat_window.py`

单 Agent 输入式聊天窗口：

- 双击桌面 Agent 打开或复用窗口。
- 上方展示该 Agent 最近单聊消息。
- 底部输入框支持回车发送。
- 发送后通过 `message_submitted` 复用 `PetManager._on_pet_chat_requested()`。
- Agent 改名或导入人格后，`set_agent_name()` 会同步窗口标题和顶部标题。

### `ui/chat_history_window.py`

可复用聊天记录窗口：

- 支持自定义标题和副标题。
- 支持加载历史消息。
- 支持追加实时消息。
- 支持清空消息。
- 当前接收带 `sender/content/kind/timestamp` 属性的消息对象，主要复用 `BusMessage`。

### `core/agent_bus.py`

旧版 `--mode agents` 的群聊总线：

- `BusMessage` 仍作为通用 UI 消息对象复用。
- `recent_history` 默认上限改为 `CHAT_UI_HISTORY_LIMIT = 50`。
- 旧版 Agent 群聊记录继续由 `AgentManager` 接入 `ChatHistoryWindow`。

## 4. API Key 与模型配置

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
- 如果 `keyring` 不可用，fallback 到当前 Windows 用户级 `QSettings`。
- 不写入项目 `.env`。

### `ui/api_key_dialog.py`

用于首次配置和随时修改 API Key。

字段：

- Provider
- Base URL
- Model
- API Key

默认桌面人格 Agent 模式的入口在系统托盘：

```text
API Key 设置
```

旧版 `--mode agents` 的入口在 Agent 右键菜单。

## 5. 已移除的工具执行能力

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

## 6. 聊天记录导入流程

默认桌面 Agent 模式新增轻量导入入口：

```text
导入人格
```

- 入口在单个桌面 Agent 右键菜单。
- 支持 `.json` / `.txt` / `.csv`。
- 使用 `PersonalityProfile` schema。
- 保存到 `models/pet_personas/<safe-agent-name>/persona.json`。
- 导入后调用 `PetCompanion.apply_profile()` 立即切换当前 Agent。
- 不保存原始聊天文本。

旧版头像 Agent 模式仍保留导入入口：

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

当前测试命令：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'; $env:PYTHONPATH = 'F:\xmlg\agent\desktop-agents'; py -m unittest discover -s "F:\xmlg\agent\desktop-agents\tests"
```

当前验证结果：

```text
Ran 123 tests
OK
```

当前测试覆盖：

- `tests/test_agent_conversation.py`
- `tests/test_agent_bus.py`
- `tests/test_api_key_dialog.py`
- `tests/test_chat_history_window.py`
- `tests/test_emotion.py`
- `tests/test_extract_wechat.py`
- `tests/test_llm_settings.py`
- `tests/test_personality.py`
- `tests/test_personality_trainer.py`
- `tests/test_pet_chat_window.py`
- `tests/test_pet_companion.py`
- `tests/test_pet_manager.py`
- `tests/test_pet_persona_importer.py`
- `tests/test_pet_selector_dialog.py`
- `tests/test_pet_widget.py`

## 8. 当前重点文件总览

### 默认桌面人格 Agent 模式

- `main.py`
- `config.py`
- `core/pet.py`
- `core/personality_trainer.py`
- `core/pet_persona_importer.py`
- `core/emotion.py`
- `core/pet_companion.py`
- `ui/pet_selector_dialog.py`
- `ui/pet_widget.py`
- `ui/pet_manager.py`
- `ui/pet_persona_import_dialog.py`
- `ui/pet_chat_window.py`
- `ui/chat_history_window.py`

### 旧版 Agent 模式和共享能力

- `core/agent.py`
- `core/agent_bus.py`
- `core/llm_client.py`
- `core/llm_settings.py`
- `core/personality.py`
- `ui/agent_manager.py`
- `ui/agent_widget.py`
- `ui/api_key_dialog.py`
- `ui/import_dialog.py`

### 文档

- `AGENT_WORK_GUIDE.md`
- `PROGRESS.md`
- `DEVELOPMENT_LOG.md`

## 9. 当前已知限制

1. 聊天记录目前是内存记录，应用退出后清空。
2. 聊天记录暂不支持搜索、导出或持久化。
3. 自动群聊没有暂停/频率 UI。
4. 人格导入分析目前同步执行，超大导出文件可能让导入弹窗短暂卡顿。
5. 多模型目前是 OpenAI-compatible 基础配置，没有完整 Provider 预设 UI。
6. API Key fallback 到 QSettings 是为了解决本机 keyring 不可用问题，安全性弱于系统凭据管理器。
7. 旧版头像 Agent 的聊天记录人格导入仍是较大的功能块，后续可继续评估是否保留。
8. 当前版本不具备主动读文件、执行命令、截图能力；默认模式人格导入只读取用户明确选择的导出文件。

## 10. 下次开发建议

优先级建议：

1. 确认 1.0 范围。
2. 手动完整验证默认启动、形象选择、人格导入、单聊窗口、自动群聊、API Key 设置、群聊记录、单 Agent 记录。
3. 评估聊天记录是否需要搜索、导出或持久化。
4. 评估人格导入是否需要后台线程和更强预览。
5. 评估是否保留旧版聊天记录导入人格和旧版 `--mode agents`。
6. 用户确认 1.0 后再提交、打标签、推送。
