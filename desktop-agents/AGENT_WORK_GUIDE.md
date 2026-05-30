# Desktop Agents 使用文档

> 最后更新：2026-05-27

本文档面向用户，说明 Desktop Agents 怎么启动、怎么配置、怎么聊天、怎么导入人格。每日开发进度请看 `PROGRESS.md`，开发者维护说明请看 `DEVELOPMENT_LOG.md`。

## 1. Desktop Agents 是什么

Desktop Agents 是一个轻量桌面多 Agent 聊天应用。核心目标不是做纯宠物，而是：

```text
聊天记录 -> 蒸馏人格 Agent -> 桌面宠物/头像形象承载 -> 陪你单聊或参与群聊
```

你可以把自己或朋友的聊天记录导入，生成带有说话习惯、口头禅、常聊话题和语气的人格 Agent。桌面宠物/头像只是这些人格的可视化形象。

## 2. 启动应用

默认启动桌面人格 Agent 模式：

```powershell
py F:\xmlg\agent\desktop-agents\main.py
```

如果想启动后直接打开 Agent 管理窗口：

```powershell
py F:\xmlg\agent\desktop-agents\main.py --open-manager
```

旧版头像 Agent 模式仍保留：

```powershell
py F:\xmlg\agent\desktop-agents\main.py --mode agents
```

## 3. 第一次使用

首次没有 Agent 时，会先让你选择桌面要出现几个 Agent，支持 1-6 个。随后会按数量逐个弹出新建 Agent 窗口：

1. 输入 Agent 名字。
2. 选择基础形象类型。
3. 选择性格标签：活泼、温柔、毒舌、沉稳。
4. 可上传 6 张情绪 PNG：正常、开心、难过、困、惊讶、生气。
5. 只上传正常图也可以，其他情绪会复用正常图。
6. 确认后桌面出现这些 Agent。

自定义 PNG/JPG 形象会自动把与图片边缘连通的近白色背景抠成透明，保留角色内部白色细节。

## 4. 系统托盘菜单

默认模式启动后，系统托盘右键菜单包含：

- `API Key 设置`
- `Agent 管理`
- `群聊记录`
- `批量导入人格`
- `暂停自动群聊` / `恢复自动群聊`
- `群聊间隔`：按 Agent 节奏 / 每 15 秒 / 每 30 秒 / 每 60 秒
- `显示萌宠`
- `隐藏萌宠`
- `退出`

全局功能放在系统托盘里，单个 Agent 的聊天、记录、人格导入和情绪切换放在对应 Agent 的右键菜单里。

## 5. API Key 设置

默认模式不会因为没有 API Key 阻塞启动。没有 Key 时使用本地回复；配置 Key 后，单聊和自动群聊会使用云端 LLM。也可以在 API Key 设置里选择“仅本地回复”，此时运行时聊天不会发送到云端。

打开方式：

```text
系统托盘右键 -> API Key 设置
```

可配置字段：

| 字段 | 示例 |
| --- | --- |
| Provider | `deepseek` / `openai` / `claude-compatible` |
| Base URL | `https://api.deepseek.com/v1` |
| Model | `deepseek-chat` |
| API Key | 你的模型 API Key |
| 回复模式 | 云端增强 / 仅本地回复 |

隐私提示：云端增强会发送当前对话、人格提示、最近聊天历史和相关记忆给配置的 API 服务商；人格导入时的原始聊天记录不会上传。

按钮行为：

- `测试 Key`：只验证 Key 是否可用，不保存、不关闭窗口。
- `保存`：先验证 Key，可用后才保存并关闭。
- 验证失败：显示失败原因，不保存。

安全行为：

- API Key 输入框是密码模式。
- 已保存的 Key 不会回填明文，只会显示占位符。
- 如果已有 Key，输入框留空时会继续使用旧 Key，不会覆盖旧 Key。
- API Key 优先保存到系统凭据管理器；不可用时保存到当前 Windows 用户配置。
- API Key 不写入项目文件。

## 6. 和单个 Agent 聊天

### 打开聊天窗口

双击桌面上的某个 Agent，会打开它的独立聊天窗口。

也可以右键 Agent，点击：

```text
和它说话
```

### 聊天效果

发送消息后：

- Agent 会根据你的输入更新情绪。
- 桌面气泡会显示回复。
- 聊天窗口会同步显示你和该 Agent 的消息。
- 没有 API Key 时走本地回复。
- 有 API Key 时走云端 LLM。
- 云端回复会逐字显示，像打字机一样一个字一个字出现。
- 不同性格的 Agent 吐字速度不同：活泼更快，温柔更慢，沉稳居中。
- 单聊记录按 Agent 分开保存。

## 7. 群聊

如果桌面上至少有 2 个 Agent，应用会自动进行轻量群聊。

群聊特点：

- 首次自动群聊会在启动后短暂延迟触发。
- 后续默认按当前发言 Agent 的性格决定间隔。
- 可以在系统托盘里暂停/恢复自动群聊。
- 可以在系统托盘里把自动群聊间隔切换为 15 秒、30 秒或 60 秒。
- 22:00-08:00 会自动降低群聊频率，自动群聊里的 Agent 更容易进入 sleepy 状态。
- 没有 API Key 时使用本地群聊话术。
- 有 API Key 时使用云端 LLM 生成聊天内容。
- 群聊中的情绪会影响其他 Agent 的状态。
- 群聊记录和单聊记录分开保存。

查看群聊记录：

```text
系统托盘右键 -> 群聊记录
```

群聊窗口也支持你输入消息，加入 Agent 们的群聊。

## 8. 聊天记录

当前有两类记录：

### 群聊记录

- Agent 之间自动群聊的消息。
- 你在群聊窗口发出的消息。
- 群聊通道中的 Agent 回复。
- 最近 50 条用于 UI 展示。
- 保存到 SQLite。

### 单 Agent 记录

右键某个 Agent，点击：

```text
聊天记录
```

可以查看：

- 你发给这个 Agent 的消息。
- 这个 Agent 对你的回复。
- 点击/打招呼产生的互动。
- 最近 50 条用于 UI 展示。
- 每个 Agent 单独保存，互不串扰。

## 9. 人格和情绪

当前支持的人格标签：

- 活泼
- 温柔
- 毒舌
- 沉稳

当前支持的情绪：

- normal
- happy
- sad
- sleepy
- angry
- surprised

人格会影响：

- 回复语气。
- 情绪倾向。
- 云端 prompt。
- 打字机单字速度。
- 云端回复前的思考时间。
- 自动群聊间隔。
- 云端回复长度约束。

情绪会影响：

- 桌面形象状态。
- PNG 情绪图切换。
- 呼吸、弹跳、摇摆、下沉、轻晃、上跳、抖动等动作。
- 本地回复和云端 prompt。

## 10. 导入聊天记录生成人格

右键某个桌面 Agent，点击：

```text
导入人格
```

流程：

1. 选择聊天记录导出文件。
2. 支持 `.json` / `.txt` / `.csv`。
3. 填写 `聊天记录里的联系人`，用于定位要分析的发言者。
4. 填写 `导入后 Agent 名称`，用于桌面显示名和聊天窗口标题。
5. 点击 `分析`，预览性格、口头禅、常聊话题、句式、emoji 和平均句长。
6. 点击 `确认导入`，生成 `models/pet_personas/<Agent 名字>/` 人格包。
7. 当前 Agent 会立即切换到新人格。

人格包包含：

- `manifest.json`：包信息、消息数和隐私标记。
- `persona.json`：运行时读取的人格档案。
- `style_profile.json`：派生的风格摘要。
- `examples.jsonl`：匿名风格样本，可用于未来换电脑后重新学习风格。
- `system_prompt.txt`：当前人格提示词。
- `eval_report.json`：本地隐私/质量检查摘要。

隐私说明：

- 人格包只保存蒸馏后的风格和提示词。
- 不保存原始聊天记录文本。
- 应用只读取你在文件选择器里明确选择的导出文件。
- 导入分析默认仅在本机处理，不启用云端增强。

## 11. LoRA 风格训练数据导出和训练

当前完成到 LoRA 第二阶段：可以把本地聊天记录导出成训练用 `train.jsonl`，并用命令行训练 LoRA adapter。训练出的 adapter 暂时还不会接入桌面 Agent 本地推理，推理接入是下一阶段。

示例：

```powershell
$env:PYTHONPATH='F:\xmlg\agent\desktop-agents'; py -m tools.export_lora_dataset --wxid wxid_xxx --db "D:\path\MSG.db" --out "D:\path\train.jsonl" --dry-run
```

确认摘要正常后写入：

```powershell
$env:PYTHONPATH='F:\xmlg\agent\desktop-agents'; py -m tools.export_lora_dataset --wxid wxid_xxx --db "D:\path\MSG.db" --out "D:\path\train.jsonl"
```

输出格式每行一个 ChatML 样本：

```json
{"messages":[{"role":"user","content":"今天好累"},{"role":"assistant","content":"辛苦啦，先休息一下"}]}
```

隐私注意：

- `train.jsonl` 会包含成对的原始对话片段，训练或分享前必须人工检查。
- 工具会过滤疑似密码、验证码、token、API Key 和长密钥，但不能保证 100% 清除所有敏感信息。
- 本工具只处理你显式提供的本地导出/已解密数据库文件，不会上传数据。

预览样本：

```powershell
$env:PYTHONPATH='F:\xmlg\agent\desktop-agents'; $env:PYTHONIOENCODING='utf-8'; py -m tools.preview_lora_dataset "D:\path\train.jsonl" --limit 20 --user-label "你" --assistant-label "目标"
```

安装训练依赖：

```powershell
cd F:\xmlg\agent\desktop-agents
py -m pip install -r requirements-train.txt
```

如果要用 NVIDIA GPU，建议先按本机 CUDA 版本安装匹配的 PyTorch，再安装其它训练依赖。

只校验数据集：

```powershell
$env:PYTHONPATH='F:\xmlg\agent\desktop-agents'; py -m tools.train_lora --dataset "D:\path\train.jsonl" --validate-only
```

训练 LoRA adapter：

```powershell
$env:PYTHONPATH='F:\xmlg\agent\desktop-agents'; py -m tools.train_lora --dataset "D:\path\train.jsonl" --out "F:\xmlg\agent\desktop-agents\models\lora_adapters\zhangbin" --base-model "Qwen/Qwen2.5-1.5B-Instruct" --epochs 3 --rank 8
```

后续阶段：

1. 把每个 Agent 的 adapter 路径保存到 Agent 配置。
2. 本地回复时加载对应 LoRA adapter。

## 12. Agent 管理

打开方式：

```text
系统托盘右键 -> Agent 管理
```

可以进行：

- 新建 Agent；如果当前出战少于 6 个，新 Agent 会直接出现在桌面，否则会作为候补档案保存。
- 勾选或取消勾选“出战”，多选决定哪些 Agent 出现在桌面。
- 桌面同时出战支持 1-6 个 Agent；取消出战不会删除 Agent 档案。
- 编辑 Agent 名称、性格和形象。
- 删除 Agent 档案，但至少保留 1 个 Agent。
- 导入人格。
- 重置人格：解除当前 Agent 的导入人格绑定，但不会删除人格包文件。
- 更换形象。
- 打开聊天窗口；未出战 Agent 需要先勾选出战。

## 13. 当前能力状态

| 能力 | 状态 |
| --- | --- |
| 默认桌面人格 Agent 模式 | 已支持 |
| Agent 管理 | 已支持，可新建/编辑/删除/导入人格，并用“出战”多选控制桌面显示 1-6 个 Agent |
| 自定义情绪 PNG 形象 | 已支持，正常/开心/难过/困/惊讶/生气 6 张图 |
| 边缘白底透明化 | 已支持 |
| 桌面拖动/点击/气泡 | 已支持 |
| 单 Agent 聊天窗口 | 已支持 |
| 多 Agent 自动群聊 | 已支持，可暂停/恢复、选择 15/30/60 秒间隔，并在夜间自动降频 |
| 用户加入群聊 | 已支持 |
| 群聊记录窗口 | 已支持 |
| 单 Agent 聊天记录 | 已支持 |
| SQLite 聊天持久化 | 已支持 |
| 显式记忆提取 | 已支持，提取偏好/计划/事件/事实 |
| LoRA 数据集导出和训练 | 已支持第二阶段，可导出/预览 ChatML JSONL，并用命令行训练 LoRA adapter；推理接入待做 |
| API Key 托盘配置 | 已支持 |
| API Key 测试和保存前验证 | 已支持 |
| OpenAI-compatible 基础配置 | 已支持 |
| 云端流式逐字打字机 | 已支持，每次显示 1 个字 |
| 性格化打字速度 | 已支持 |
| 默认模式人格导入 | 已支持 |
| 旧版头像 Agent 模式 | 已保留 |
| 工具执行 | 已移除 |
| 权限分级 | 已移除 |
| 截图工具 | 已移除 |

## 13. 安全建议

- 不要把 API Key、私钥、密码、验证码等敏感内容发给 Agent。
- 当前版本不会主动读取本地文件，也不会执行本地命令。
- 人格导入只读取你明确选择的聊天记录导出文件。
- API Key 优先保存到系统凭据管理器；不可用时才 fallback 到当前 Windows 用户配置。

## 14. 后续可考虑

- 中期：新增真正的本地模型后端，连接本机 Ollama/llama.cpp 等 localhost 服务；提供本地模型状态检测、测试回复、超时回退和 `local_preferred` / `cloud_preferred` 路由模式。
- 后期：把“LoRA 风格训练”包装成普通用户可理解的“本机学习风格 / 风格增强”，基于脱敏样本训练 adapter，并在运行时通过本地模型加载；训练前必须有授权、预览和更强隐私评测。
- 聊天记录搜索、导出或置顶。
- 显式记忆管理 UI。
- 微博每日热点 API 接入，作为可选群聊主题来源。
- 托盘 token 消耗统计。
- 人格导入的大文件分析改为后台线程。
- 是否保留旧版头像 Agent 的聊天记录导入人格。
