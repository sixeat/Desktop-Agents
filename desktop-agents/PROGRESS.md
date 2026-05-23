# Desktop Agents 进度记录

> 更新时间：2026-05-23

## 今日完成

### 1. 聊天记录人格导入流程调整

- 将微信导入流程改为以本地聊天记录文件为主。
- 移除应用内自动下载 wx-mcp。
- 保留 wx-mcp 作为参考方案，只在界面中提示链接：
  - https://github.com/r266-tech/wechat-local-mcp
- 导入弹窗按钮调整为：
  - `导入聊天记录文件`
  - `批量导入`
- 支持格式：
  - `txt`
  - `csv`
  - `json`
  - `sqlite`
  - `db`
  - `sqlite3`

### 2. Agent 工具执行能力

已让 Agent 不仅能聊天，还能通过 Function Calling 选择工具执行任务。

新增核心能力：

- 每个 Agent 拥有独立工具集。
- 支持 OpenAI-compatible / DeepSeek 风格的 `tool_calls`。
- 新增 `ToolExecutor`。
- 新增权限等级：
  - `SAFE`：免确认
  - `NORMAL`：普通确认
  - `DANGEROUS`：高危确认

内置工具：

- `read_file`
  - 读取项目目录内文本文件。
  - 默认拒绝 `.env`、密钥、证书等敏感文件。
- `execute_command`
  - 执行结构化命令。
  - 不使用 `shell=True`。
  - 每次高危确认。
  - 限制 cwd、超时和输出大小。
- `screenshot`
  - 通过 GUI 线程截图。
  - 当前返回截图文件路径和尺寸信息。

### 3. 工具权限 UI

新增工具权限确认弹窗：

- 普通工具显示普通确认。
- 高危工具显示更强风险提示。
- 用户拒绝后工具不会执行。
- 工具状态会以简短系统消息广播，不泄露完整文件内容或命令输出。

### 4. 多模型基础支持

将原 DeepSeek 客户端抽象为 OpenAI-compatible 客户端：

- 新增 `OpenAICompatibleClient`。
- 保留 `DeepSeekClient` 兼容别名。
- 支持通过环境变量配置：
  - `LLM_PROVIDER`
  - `LLM_API_KEY`
  - `LLM_BASE_URL`
  - `LLM_MODEL`
- 兼容旧环境变量：
  - `DEEPSEEK_API_KEY`
  - `DEEPSEEK_BASE_URL`
  - `DEEPSEEK_MODEL`

### 5. 启动检测 + Key 管理

新增启动配置流程：

- 启动时检测是否已配置 API Key。
- 若未配置，先弹出“首次使用配置”。
- 如果用户取消配置，应用干净退出，不创建 Agent。
- 右键菜单和托盘菜单新增：
  - `API Key 设置`
- 保存后会热更新当前 Agent 的模型客户端。

配置持久化：

- Provider / Base URL / Model 保存到 `QSettings`。
- API Key 优先保存到系统凭据管理器 `keyring`。
- 如果 `keyring` 不可用，fallback 保存到当前 Windows 用户配置。
- 不写入项目 `.env`。
- API Key 输入框默认密码模式，已有 Key 只显示遮罩。

### 6. 使用文档

新增持续更新文档：

- `AGENT_WORK_GUIDE.md`

文档内容包括：

- 如何启动项目
- 如何配置 API Key
- 如何让 Agent 读文件、执行命令、截图
- 多 Agent 分工方式
- 常见 Prompt 示例
- 权限等级说明
- 安全建议
- 当前能力状态

### 7. 测试与验证

今日最终测试结果：

```text
py -m compileall F:\xmlg\agent\desktop-agents
OK

py -m unittest discover -s F:\xmlg\agent\desktop-agents\tests
Ran 45 tests
OK
```

## 当前项目状态

| 模块 | 状态 |
| --- | --- |
| 多 Agent 桌面聊天 | 已完成 |
| 群聊记录窗口 | 已完成 |
| 人格配置和切换 | 已完成 |
| 聊天记录导入人格 | 已完成 |
| API Key 首次配置 | 已完成 |
| API Key 管理 | 已完成 |
| 多模型基础配置 | 已完成 |
| 工具调用框架 | 已完成 |
| 文件读取工具 | 已完成 |
| 命令执行工具 | 已完成 |
| 截图工具 | 已完成基础版 |
| 长期任务队列 | 未开始 |
| 截图视觉理解 / OCR | 未开始 |
| 更细的 per-Agent 工具配置 UI | 未开始 |

## 下次可以继续的方向

1. **长期任务队列**
   - 让 Agent 接收任务后持续执行。
   - 支持任务状态：待办 / 执行中 / 完成 / 失败。
   - 支持任务进度展示。

2. **工具能力增强**
   - 文件搜索工具。
   - 项目结构分析工具。
   - 浏览器/网页读取工具。
   - OCR 或视觉模型接入截图。

3. **多模型管理增强**
   - Provider 下拉选择。
   - 常见模型预设。
   - 测试连接按钮。
   - 每个 Agent 使用不同模型。

4. **Agent 工作流**
   - 给每个 Agent 设置角色分工。
   - 一个 Agent 负责规划，一个负责执行，一个负责测试。
   - 增加“任务分配”和“结果汇总”。

5. **安全增强**
   - 更严格命令 allowlist。
   - 工具调用日志。
   - 每个工具单独开关。
   - DANGEROUS 操作二次确认或输入确认短语。

## 备注

- 当前命令执行只是应用层限制，不是系统级强沙箱。
- API Key fallback 到 QSettings 是为了解决当前 Windows 环境 keyring 后端不可用的问题。
- 项目不会主动下载 wx-mcp，只提供参考链接。
