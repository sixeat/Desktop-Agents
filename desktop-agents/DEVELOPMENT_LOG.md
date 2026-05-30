# Desktop Agents 开发文档

> 日期：2026-05-27

本文档面向开发者，记录当前架构、核心模块、调用链、测试和维护约定。每日进度请看 `PROGRESS.md`，用户操作说明请看 `AGENT_WORK_GUIDE.md`。

## 1. 项目定位

Desktop Agents 是轻量桌面多 Agent 聊天应用。项目主线是：

```text
聊天记录 -> 人格 Agent -> 桌面宠物/头像形象承载 -> 单聊/群聊/记忆陪伴
```

宠物/头像不是产品本体，而是人格 Agent 的默认可视化载体。后续可以替换为自定义宠物、头像或其他桌面形象。

当前默认运行模式是 `pets`，旧版头像 Agent 模式保留在 `--mode agents`。

## 2. 运行入口

### 默认桌面人格 Agent 模式

```text
main.py
  -> run_pet_mode()
  -> pet_registry.load_pet_configs()
  -> AgentEditDialog（首次无 Agent 时）
  -> PetManager
  -> PetWidget
  -> PetCompanion
  -> ReplyRouter
  -> ChatStorage / ExplicitMemoryStore
  -> OpenAICompatibleClient（配置 API Key 后）
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

旧版模式保留兼容，但当前产品重心在默认桌面人格 Agent 模式。

## 3. 核心聊天链路

### 单 Agent 聊天

```text
PetWidget 双击
  -> PetWidget.chat_window_requested
  -> PetManager.show_pet_chat_window()
  -> PetChatWindow.message_submitted
  -> PetManager._on_pet_chat_requested()
  -> 写入 direct_histories 和 SQLite direct channel
  -> ExplicitMemoryStore.remember_user_message()
  -> ReplyRouter.decide()
  -> 无 API Key: LocalReplyBackend.reply()
  -> 有 API Key: CloudReplyBackend.reply_stream()
  -> PetManager 逐字更新桌面气泡和聊天窗口 partial 行
  -> 最终 PetResponse 只持久化一次
```

维护约定：

- 流式 partial 只更新 UI，不写入 SQLite。
- 最终回复只写入一条 Agent 消息。
- direct 消息必须带当前 Agent identity，避免多个同类型 Agent 串记录。

### 多 Agent 自动群聊

```text
PetManager.start_auto_chat()
  -> 检查用户是否暂停自动群聊
  -> 根据手动间隔或当前发言 Agent 性格决定下一次群聊间隔
  -> 夜间 22:00-08:00 自动放大间隔
  -> PetManager.run_auto_chat_once()
  -> ReplyRouter.decide()
  -> 无 API Key: LocalReplyBackend.reply()
  -> 有 API Key: CloudReplyBackend.reply_stream(..., channel="group")
  -> PetManager 逐字更新桌面气泡和群聊 partial 行
  -> 最终 PetResponse 只持久化一次
  -> 写入 group_history 和 SQLite group channel
```

维护约定：

- group 记录和 direct 记录必须分离。
- 自动群聊的 Agent 回复不应写入某个 Agent 的 direct 历史。
- 默认群聊间隔由 `core/personality_rhythm.py` 控制。
- `_auto_chat_interval_override_ms` 为会话级手动间隔，优先级高于性格化随机间隔。
- `_auto_chat_paused_by_user` 表示用户显式暂停，`show_all()`、新增 Agent、切换出战都不能绕过它自动重启群聊。
- 夜间 22:00-08:00 会通过 `_effective_auto_chat_interval()` 降低频率，并只对自动群聊 response 应用 sleepy mood。

### 人格导入

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

维护约定：

- 只保存蒸馏后的人格档案和 prompt。
- 不保存原始聊天记录文本。
- `聊天记录里的联系人` 和 `导入后 Agent 名称` 是两个概念，不能混用。

## 4. 关键模块

### `core/pet.py`

桌面人格 Agent 的基础配置：

- `PetMood`
- `PetDefinition`
- `PetConfig`
- 默认形象类型
- 默认性格映射
- 可选性格标签

### `core/personality_trainer.py`

聊天记录蒸馏人格的核心模块：

- `PersonalityProfile`
- `PersonalityTrainer.analyze()`
- 默认人格 `_default_profile()`
- System Prompt 构建
- JSON save/load

`jieba` 是可选依赖；没有安装时使用正则 fallback。

### `core/pet_persona_importer.py`

人格导入适配层：

- 接收 `.json` / `.txt` / `.csv` 文件或目录。
- 复用 `tools.wechat.parsers.load_export_dir()`。
- 优先使用目标联系人消息；目标消息太少时 fallback 到全部可读取文本消息。
- 生成并保存 `PersonalityProfile`。

### `core/emotion.py`

情绪识别和情绪提示：

- 支持 normal / happy / sad / sleepy / angry / surprised。
- 根据用户输入和人格标签调整情绪倾向。
- 为 LLM prompt 提供 mood prompt。

### `core/personality_rhythm.py`

性格化节奏参数：

- `RhythmProfile`
- `RHYTHM_TABLE`
- `get_rhythm()`
- `get_typing_delay()`
- `get_chat_interval()`
- `get_thinking_time()`

当前规则：所有性格都严格逐字输出，每次只显示 1 个字；性格差异体现在单字间隔、波动、思考时间、群聊间隔和最大回复长度。

### `core/pet_companion.py`

桌面人格 Agent 的对话核心：

- 维护 `PetConfig`、人格档案、情绪引擎和当前情绪。
- `handle_interaction()` 处理本地点击、打招呼、群聊和无 Key 聊天。
- `chat()` 处理非流式 LLM 聊天，异常时 fallback 本地回复。
- `build_messages()` 注入人格 prompt、当前 mood、显式记忆和性格化回复长度约束。
- `remember_exchange()` 支持流式完成后只记录一次完整对话轮次。
- `history` 只作为 LLM 上下文历史，受 `PET_CHAT_HISTORY_LIMIT` 控制。

维护约定：不要把 UI 详细聊天记录直接当作无限上下文塞进 `PetCompanion.history`。

### `core/reply_router.py`

本地/云端回复路由：

- `ReplyRequest`
- `RouteDecision`
- `ReplyRouter`
- `CloudReplyBackend`
- `LocalReplyBackend`
- `CloudReplyBackend.reply_stream()`

当前兼容策略：默认模式有 API Key 走云端，无 API Key 走本地；用户也可以在 API 设置里选择 `local_only`，强制运行时聊天不发送到云端。

中期扩展方向（尚未实现）：

```text
ReplyRouter
  -> CloudReplyBackend（当前 API 路径）
  -> LocalModelBackend（未来本地模型服务）
  -> LocalReplyBackend（当前模板兜底）
```

目标是让 `LocalModelBackend` 独立于当前模板本地回复，优先接本机 localhost/OpenAI-compatible 服务，例如 Ollama 或 llama.cpp server。未来设置可包括 `local_model/enabled`、`local_model/base_url`、`local_model/model`、timeout 和 health status。健康检查必须非阻塞并缓存状态，启动时本地服务不可用不能卡住桌面应用。

未来路由模式可以扩展为：

- `local_only`：只走本地模型/模板，不发送运行时聊天上下文到云端。
- `cloud_when_key`：当前默认兼容模式，有 Key 走云端。
- `local_preferred`：本地模型可用时优先本地，失败再考虑云端。
- `cloud_preferred`：云端优先，失败后走本地模型/模板。

隐私边界：人格导入和包生成默认本地处理，不上传原始聊天；运行时云端回复会发送当前对话、人格 prompt、最近历史和相关记忆给配置的 provider。

### `core/chat_storage.py`

SQLite 聊天持久化：

- direct/group 分通道保存。
- 每个单聊按 Agent identity 隔离。
- 启动时加载最近 50 条用于 UI 和 LLM 上下文恢复。
- 使用短连接，避免 Windows 下 SQLite 文件锁影响测试清理。

### `core/explicit_memory.py`

显式记忆提取和召回：

- 从用户消息提取 preference / plan / event / fact。
- 支持相关记忆召回。
- 支持定时 follow-up。
- 过滤密码、验证码、token、API Key、密钥等敏感信息。

### `core/llm_client.py`

OpenAI-compatible LLM 客户端：

- `complete()`：非流式回复。
- `chat()`：返回文本。
- `chat_stream()`：解析 SSE delta 并 yield 文本片段。
- `validate_api_key()`：发送最小请求验证 Key 可用性。
- 请求使用 `trust_env=True`，支持系统代理环境。

### `core/llm_settings.py`

LLM 配置读取和保存：

- 环境变量优先。
- API Key 优先保存到系统凭据管理器。
- keyring 不可用时 fallback 到当前 Windows 用户级 `QSettings`。
- Provider / Base URL / Model 保存到 `QSettings`。
- 不写入项目 `.env`。

## 5. LoRA 数据集导出

当前实现到 LoRA 第二阶段：导出/预览训练数据，并提供离线训练脚本；桌面 Agent 推理接入仍未实现。

```text
tools.export_lora_dataset
  -> tools.wechat.parsers.load_messages()/load_export_dir()
  -> core.lora_dataset.build_lora_dataset()
  -> core.lora_dataset.write_lora_jsonl()

tools.preview_lora_dataset
  -> core.lora_dataset.read_lora_jsonl()
  -> core.lora_dataset.format_lora_preview()

tools.train_lora
  -> core.lora_dataset.read_lora_jsonl()
  -> validate_lora_examples()
  -> lazy import torch/transformers/peft
  -> PEFT LoRA training
  -> models/lora_adapters/<name>/
```

维护约定：

- `core/lora_dataset.py` 保持纯函数，负责消息清洗、敏感内容过滤、user/assistant 配对和 JSONL 写入。
- 复用 `tools.wechat.parsers.clean_message_text()` 过滤媒体占位、XML 和非文本。
- 复用 `core.explicit_memory.ExplicitMemoryStore.SENSITIVE_PATTERN` 过滤密码、验证码、token、API Key、`sk-...` 和长密钥。
- 目标联系人消息映射为 `assistant`，非目标消息映射为 `user`。
- 只导出有上一条 user 上下文的目标回复，跳过 target-only monologue。
- `tools/export_lora_dataset.py` 必须默认拒绝覆盖输出文件，并在非 quiet 模式打印隐私提示。
- `tools/train_lora.py` 顶层不能 import `torch`、`transformers`、`peft`、`datasets`；训练依赖只能在训练路径懒加载。
- 训练依赖放在 `requirements-train.txt`，不加入主 `requirements.txt`。
- `--validate-only` 必须不检查 ML 依赖，方便普通环境验证数据集。
- 训练脚本第一版使用 full-sequence SFT；后续可优化为 assistant-only loss masking。

长期风格学习路线（尚未接入运行时）：

- 普通用户界面应称为“本机学习风格 / 风格增强”，不要直接暴露 LoRA、rank、batch size、量化等术语。
- 人格包里的 `examples.jsonl` 是安全迁移种子；真正训练前需要更强的匿名对话轮次抽取、授权确认和人工预览。
- 训练前评测需要覆盖 PII、原始样本复述、n-gram/相似度重叠、真实身份冒充声明、源聊天引用等风险。
- 未来 `adapter/` 需要记录 base model、adapter version、dataset/package hash、创建时间、兼容 runtime 和迁移信息。
- LoRA adapter 运行时依赖中期本地模型后端；在没有 LocalModelBackend 前，不应把 adapter 接进 `ReplyRouter`。
- 跨电脑迁移应优先使用脱敏人格包重新学习，而不是把原始聊天记录或不可解释的本地缓存一起复制。

## 6. UI 模块

### `ui/pet_manager.py`

默认模式主控制器：

- `self.pets` 保存全量 Agent 档案 roster。
- `self.widgets` 只保存当前出战、实际显示在桌面的 `PetWidget`。
- 创建和定位已出战 Agent 的 `PetWidget`。
- 创建已出战 Agent 的 `PetCompanion`。
- 管理系统托盘和 `Agent 管理` 窗口。
- 通过 `PetConfig.deployed` 持久化“出战/休息”状态，限制同时出战 1-6 个 Agent。
- 管理自动群聊暂停/恢复、手动间隔 override 和夜间降频。
- 路由本地/LLM 聊天。
- 管理云端流式逐字打字机状态。
- 根据 Agent 性格控制单字打字速度、thinking delay 和自动群聊间隔。
- 管理 SQLite 聊天持久化和显式记忆提取。
- 管理单聊窗口、群聊窗口和人格导入。

### `ui/pet_widget.py`

桌面形象层：

- 默认圆形形象和名字标签。
- 6 情绪 PNG 形象。
- 边缘连通近白色背景透明化。
- 呼吸、弹跳、摇摆、下沉、轻晃、上跳、抖动等动画。
- 拖动、点击、双击聊天、右键菜单。
- 流式气泡复用和更新。

### `ui/pet_chat_window.py`

单 Agent 输入式聊天窗口：

- 加载最近单聊消息。
- 回车发送消息。
- 支持流式 partial 临时消息行。
- Agent 改名或导入人格后同步标题。

### `ui/chat_history_window.py`

可复用聊天记录窗口：

- 用于群聊记录和单 Agent 历史记录。
- 支持加载、追加、清空消息。
- 支持流式 partial 临时消息行。
- 可选输入框用于用户加入群聊。

### `ui/api_key_dialog.py`

API Key 配置和验证弹窗：

- `测试 Key` 只验证，不保存、不关闭。
- `保存` 会先验证，成功后才写入设置并关闭。
- 验证失败显示错误原因，不保存。
- 已有 Key 只显示占位符，不回填明文。
- 输入框留空时继续使用旧 Key，不覆盖旧 Key。

## 7. 已移除能力

当前精简版已移除：

- 工具执行框架。
- 权限分级系统。
- 工具权限确认弹窗。
- 读文件工具。
- 执行命令工具。
- 截图工具。
- 模型 tool_calls 调用循环。

因此默认桌面 Agent 不会主动读文件、执行命令或截图。

## 7. 测试

完整测试命令：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'; $env:PYTHONPATH = 'F:\xmlg\agent\desktop-agents'; py -m unittest discover -s "F:\xmlg\agent\desktop-agents\tests"
```

当前结果：

```text
Ran 201 tests
OK
```

重点测试：

- `tests/test_reply_router.py`
- `tests/test_chat_storage.py`
- `tests/test_explicit_memory.py`
- `tests/test_personality_rhythm.py`
- `tests/test_llm_client.py`
- `tests/test_api_key_dialog.py`
- `tests/test_pet_manager.py`
- `tests/test_pet_companion.py`
- `tests/test_pet_widget.py`
- `tests/test_pet_chat_window.py`
- `tests/test_chat_history_window.py`

## 8. 当前限制和后续开发点

- 聊天记录已持久化到 SQLite，但暂不支持搜索、导出或置顶。
- 显式记忆已能提取偏好/计划/事件/事实，但还没有完整的记忆管理 UI。
- 自动群聊没有暂停/频率 UI。
- 人格导入分析目前同步执行，超大导出文件可能让导入弹窗短暂卡顿。
- 多模型目前是 OpenAI-compatible 基础配置，没有完整 Provider 预设 UI。
- API Key fallback 到 QSettings 是为了兼容 keyring 不可用场景，安全性弱于系统凭据管理器。
- 托盘 token 消耗统计暂缓；需要先统一保存非流式和流式 usage。
- 微博每日热点可作为后续可选群聊主题来源，需要设计开关、缓存、限流和内容过滤。
