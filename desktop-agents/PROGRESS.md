# Desktop Agents 进度文档

> 更新时间：2026-05-27

本文件只记录每日进度，最新日期在最上面。每一天只写三类内容：今天新做的、今天验证的、后续待做/想法。稳定的功能说明放到 `AGENT_WORK_GUIDE.md`，架构和维护说明放到 `DEVELOPMENT_LOG.md`。

## 2026-05-29

### 今天新做的

- 前期人格包体验继续产品化：单个导入预览展示人格包文件、隐私标记、脱敏计数和本机处理说明。
- 批量导入新增授权确认，未确认前不能扫描或生成人格包。
- API Key 设置新增运行时隐私说明和回复模式：默认有 Key 使用云端增强，也可切换为“仅本地回复”。
- Agent 管理新增“重置人格”，只解除当前 Agent 的 `persona_path` 绑定，不删除人格包文件。
- 开发文档记录中期本地模型后端和后期 LoRA/风格增强路线，明确本轮不实现 LocalModelBackend 或 adapter runtime。
- 修复启动卡顿：自定义情绪 PNG 头像的白底透明 flood-fill 在原始大图尺寸上执行，导致 `create_widgets()` 耗时 42 秒。改为先缩放到 `PET_SIZE(80x80)` 再做透明处理，耗时降至约 0.44 秒，启动提速约 95 倍。
- 修复新建/编辑 Agent 性格下拉框不显示文字：`theme.py` 中 `QComboBox` 的 `padding` 过大挤占了文字区域，调整 padding 并增加 `min-height` 和 `QComboBox::drop-down` 样式。
- 优化批量导入说明：明确列出支持的文件类型（.txt/.json/.csv/.db/.sqlite），扫描为空时给出排查提示。
- 新增人格库窗口：`ui/persona_library_dialog.py`，列出 `models/pet_personas/` 下所有人格包，显示名称/性格/消息数/创建时间/路径，支持删除和绑定到 Agent。入口在系统托盘和 Agent 管理。批量导入入口从系统托盘移入人格库内。

### 今天验证的

- 已增加对应 focused unittest，完整验证结果以本轮执行记录为准。
- 启动计时验证：`create_widgets` 从 42.3s 降至 0.44s。
- 完整回归 236 tests OK。

### 后续待做/想法

- 手动验证批量导入授权、API 回复模式切换、Agent 管理重置人格。
- 中期再做本地模型服务检测和 `LocalModelBackend`。
- 后期再把 LoRA/adapter 以“本机学习风格”方式接入本地模型运行时。

## 2026-05-28

### 今天新做的

- 完成 LoRA 第二阶段训练脚本：新增 `tools/train_lora.py`。
- 新增可选训练依赖文件 `requirements-train.txt`，避免普通桌面应用强制安装 `torch/transformers/peft`。
- 训练脚本支持 `--validate-only`、`--dry-run`、`--overwrite`、`--base-model`、`--epochs`、`--rank`、`--batch-size`、`--learning-rate`、`--max-length`。
- 训练依赖改为懒加载：未安装 ML 依赖时，桌面应用和数据集校验仍可正常运行。
- 新增 `tools.preview_lora_dataset`，可把 JSONL 样本预览成“你 / 目标”的对话格式。
- 优化 LoRA 数据集噪声过滤，排除 `[其他消息]`、表情包占位、商品分享、点击链接、淘口令、撤回消息和引用片段。
- 使用 `F:\xmlg\agent\ltjl\私聊_张斌.txt` 生成 `F:\xmlg\agent\ltjl\train_zhangbin.jsonl`，清洗后得到 797 条训练样本。

### 今天验证的

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'; $env:PYTHONPATH = 'F:\xmlg\agent\desktop-agents'; py -m unittest "F:\xmlg\agent\desktop-agents\tests\test_lora_dataset.py" "F:\xmlg\agent\desktop-agents\tests\test_train_lora.py"
```

定向测试结果：

```text
Ran 16 tests
OK
```

完整回归结果：

```text
Ran 217 tests
OK
```

真实张斌数据集校验：

```powershell
$env:PYTHONPATH='F:\xmlg\agent\desktop-agents'; py -m tools.train_lora --dataset "F:\xmlg\agent\ltjl\train_zhangbin.jsonl" --validate-only
```

结果：

```text
样本数：797
user 平均字符数：6.4
assistant 平均字符数：7.1
建议：样本量适合第一版 LoRA 试训。
```

### 后续待做/想法

- 安装训练依赖后，实际运行 `tools.train_lora` 训练 `zhangbin` adapter。
- 第三阶段把 LoRA adapter 路径接入 Agent 配置和本地回复。
- 后续优化训练 loss：从 full-sequence SFT 改为 assistant-only loss masking。

## 2026-05-27

### 今天新做的

- Agent 管理新增“出战”勾选列，支持像游戏队伍一样多选哪些 Agent 出现在桌面。
- Agent 档案和桌面显示状态分离：取消出战只隐藏桌面 Agent，不删除档案、人格、形象或聊天记录。
- 桌面同时出战数量限制为 1-6 个；少于 1 个或超过 6 个时会提示并自动恢复勾选状态。
- 新增 Agent 时，如果当前出战未满 6 个会直接出现在桌面；如果已满 6 个，会保存为候补档案。
- Agent 管理里的编辑、删除、导入人格、更换形象、打开聊天改为按 Agent 档案 ID 工作，未出战的 Agent 也能编辑、导入人格和换形象。
- 启动时只创建已出战 Agent 的桌面窗口，但仍保留全部 Agent 档案配置。
- 系统托盘新增自动群聊控制：暂停/恢复自动群聊。
- 系统托盘新增群聊间隔选择：按 Agent 节奏、每 15 秒、每 30 秒、每 60 秒。
- 自动群聊在 22:00-08:00 自动降频，并让自动群聊回复更容易呈现 sleepy 状态。

### 今天验证的

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'; $env:PYTHONPATH = 'F:\xmlg\agent\desktop-agents'; py -m unittest discover -s "F:\xmlg\agent\desktop-agents\tests"
```

结果：

```text
Ran 201 tests
OK
```

新增/更新测试覆盖：

- `tests/test_agent_management_dialog.py`
- `tests/test_pet_manager.py`

### 后续待做/想法

- 手动验证 Agent 管理窗口里的多选出战：勾选/取消勾选、超过 6 个提示、最后 1 个不能取消、未出战 Agent 仍可编辑和导入人格。
- 后续可考虑给未出战 Agent 增加“休息中”状态说明，或者在聊天入口提示用户先勾选出战。

## 2026-05-26

### 今天新做的

- 实现云端流式打字机效果：云端 LLM 回复会逐步显示在桌面气泡、单聊窗口和群聊窗口中。
- 流式过程中只更新 UI，不写入 SQLite；最终回复完成后只保存一条完整 Agent 消息。
- 桌面气泡复用同一个流式气泡，避免 partial chunk 创建多个气泡。
- 聊天窗口和群聊记录窗口支持临时 partial 行，最终消息落库后清理临时行。
- 打字机效果最终调整为严格逐字展示：每次只显示 1 个字。
- 新增 `core/personality_rhythm.py`，支持性格 × 节奏系统。
- 活泼、毒舌、温柔、沉稳拥有不同单字打字间隔、波动、群聊间隔、思考时间和最大回复长度。
- `PetManager` 根据当前 Agent 性格决定流式打字速度、云端回复前 thinking delay、自动群聊间隔。
- `PetCompanion.build_messages()` 增加性格化回复长度提示。
- API Key 设置弹窗新增 `测试 Key` 按钮。
- 点击保存时会先验证 API Key，可用后才保存并关闭。
- 验证失败时显示失败原因，不保存、不关闭弹窗。
- API Key 输入框保持密码模式；已有 Key 只显示占位符，不回填明文。
- 留空 API Key 输入框时，会继续使用已保存 Key 测试或保存，不覆盖旧 Key。
- LLM 客户端新增 `LLMValidationResult` 和 `validate_api_key()`。
- 新增 `core/reply_router.py`，建立云端/本地回复路由骨架。
- 当前路由策略保持兼容：有 API Key 走云端，无 API Key 走本地。
- 显式记忆上下文通过 `ReplyRequest` 进入云端 prompt。
- 新增 `core/chat_storage.py`，用 SQLite 持久化 direct/group 对话。
- 新增 `core/explicit_memory.py`，从用户消息中提取偏好、计划、事件和事实。
- 显式记忆支持相关召回和定时 follow-up，并过滤密码、验证码、token、API Key、密钥等敏感信息。
- 更新文档结构：进度文档、开发文档、使用文档分工明确。
- 桌面 Agent 数量改为支持 1-6 个：首次无 Agent 时先选择数量，再逐个创建；Agent 管理里最多新增到 6 个，至少保留 1 个。

### 今天验证的

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'; $env:PYTHONPATH = 'F:\xmlg\agent\desktop-agents'; py -m unittest discover -s "F:\xmlg\agent\desktop-agents\tests"
```

结果：

```text
Ran 190 tests
OK
```

新增/更新测试覆盖：

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

### 后续待做/想法

- 托盘 token 消耗统计暂缓实现。
  - 原因：当前 `complete()` 和 `chat_stream()` 尚未统一保存 provider 返回的 usage，尤其流式 usage 在 OpenAI-compatible provider 间不完全一致。
  - 后续建议先新增 `core/llm_usage.py`，可靠统计请求数和 token usage 后再放入托盘菜单。
- 继续评估云端/本地路由：后续目标是有网和深度话题走云端，无网或简单对话走本地 Qwen/LoRA。
- 微博每日热点想法：后续可调用微博 API 查询每日热点，作为可选群聊主题来源。
  - 热点不应强制驱动群聊，而是做成用户可选开关。
  - 需要考虑频率限制、热点缓存、内容安全过滤、是否显示热点来源，以及用户是否手动选择某条热点作为群聊主题。
- 需要继续手动验证：默认启动、Agent 管理、人格式导入、单聊窗口、群聊窗口、API Key 验证、流式逐字效果、SQLite 恢复。

## 2026-05-25

### 今天新做的

- 当天未单独维护进度记录；当前可追溯记录从 2026-05-24 继续。

### 今天验证的

- 无单独记录。

### 后续待做/想法

- 后续每天更新时按倒序追加：最新日期在最上方，旧日期保留在下方。

## 2026-05-24

### 今天新做的

- 默认启动进入桌面人格 Agent 模式。
- 默认启动会读取已保存的 Agent 配置；首次无 Agent 时弹出新建 Agent 窗口。
- 支持单个 Agent 单独新建、编辑、删除和管理。
- 新建/编辑时可设置名字、基础类型、性格标签和 6 张情绪 PNG 形象。
- 6 张情绪形象对应：正常、开心、难过、困、惊讶、生气。
- 只配置正常 PNG 时，其他情绪会自动复用正常图。
- 头像图片会自动把与图片边缘连通的近白色背景抠成透明。
- 桌面显示用户创建的 Agent，不再强制固定 3 个不同类型。
- 桌面 Agent 支持拖动、点击、呼吸动画、情绪切换、情绪动作和桌面气泡。
- 旧版头像 Agent 模式保留在 `--mode agents`。
- 新增人格训练器，可从聊天文本分析口头禅、句式、emoji、话题、平均句长和打招呼风格。
- 无人格文件时按形象类型生成默认人格。
- System Prompt 包含名字、类型、性格、口头禅、话题和语气约束。
- 新增情绪引擎，支持 happy / sad / sleepy / angry / surprised。
- 用户输入会触发情绪变化并影响桌面 Agent 表情。
- 人格和情绪会共同影响本地回复风格。
- 默认桌面 Agent 模式不强制配置 API Key。
- 没有 API Key 时使用本地回复；配置 API Key 后，单 Agent 聊天和自动群聊使用配置好的 LLM。
- API Key 设置入口放在系统托盘右键菜单。
- LLM 调用在后台线程执行，完成后回到 UI 线程更新气泡、情绪和聊天记录。
- LLM 异常时回退到本地回复，不展示技术错误。
- 新增群聊记录窗口和每个桌面 Agent 的独立单聊记录窗口。
- 群聊和单聊分开保存，互不串扰。
- UI 详细记录只保留最新 50 条。
- 系统托盘新增 `群聊记录` 入口。
- 桌面 Agent 右键菜单新增 `聊天记录` 入口。
- LLM 异步回复按 `group` / `direct` 通道写入正确记录。
- 默认桌面 Agent 右键菜单新增 `导入人格`。
- 支持选择 `.json` / `.txt` / `.csv` 微信聊天记录导出文件。
- 导入时 `聊天记录里的联系人` 和 `导入后 Agent 名称` 分开填写。
- 导入前可预览性格、口头禅、话题、句式、emoji、平均句长和分析消息数。
- 确认导入后保存 `models/pet_personas/<Agent 名字>/persona.json`。
- 保存内容是蒸馏后的人格档案和 prompt，不保存原始聊天记录。
- 导入后只切换当前选中的桌面 Agent，并立即按新人格说话。
- 双击桌面 Agent 可打开独立单聊窗口，支持输入消息和查看最近单聊记录。
- Agent 改名或导入人格后，已打开的聊天窗口标题会同步刷新。
- 旧版 `--mode agents` 模式仍可启动。
- 旧版 `AgentBus` 群聊历史上限调整为 50 条。
- 聊天记录人格导入能力保留。
- 工具执行、权限分级、截图、tool_calls 循环等过度设计能力保持移除。
- 更新 `AGENT_WORK_GUIDE.md`、`PROGRESS.md`、`DEVELOPMENT_LOG.md`。

### 今天验证的

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'; $env:PYTHONPATH = 'F:\xmlg\agent\desktop-agents'; py -m unittest discover -s "F:\xmlg\agent\desktop-agents\tests"
```

结果：

```text
Ran 123 tests
OK
```

### 后续待做/想法

- 收敛 1.0 范围。
- 手动完整验证默认启动、形象选择、人格导入、单聊窗口、自动群聊、API Key 设置、群聊记录、单 Agent 记录。
- 评估聊天记录搜索、导出或持久化。
- 评估人格导入是否需要后台线程和更强预览。
- 评估是否保留旧版聊天记录导入人格和旧版 `--mode agents`。
- 用户确认 1.0 后再提交、打标签、推送。
