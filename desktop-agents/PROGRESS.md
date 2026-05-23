# Desktop Agents 进度记录

> 更新时间：2026-05-23

## 当前定位

Desktop Agents 当前调整为轻量桌面多 Agent 聊天应用。`v0.1` 已作为备选版本保留在 GitHub；后续精简完成并确认 1.0 后再推送。

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

### 2. 多模型基础支持

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

### 3. 启动检测 + Key 管理

新增启动配置流程：

- 启动时检测是否已配置 API Key。
- 若未配置，先弹出“首次使用配置”。
- 如果用户取消配置，应用干净退出，不创建 Agent。
- 右键菜单保留 `API Key 设置`。
- 保存后会热更新当前 Agent 的模型客户端。

配置持久化：

- Provider / Base URL / Model 保存到 `QSettings`。
- API Key 优先保存到系统凭据管理器 `keyring`。
- 如果 `keyring` 不可用，fallback 保存到当前 Windows 用户配置。
- 不写入项目 `.env`。
- API Key 输入框默认密码模式，已有 Key 只显示遮罩。

### 4. 精简过度设计功能

已移除：

- 工具执行框架
- 权限分级系统
- 工具权限弹窗
- 读文件工具
- 执行命令工具
- 截图工具
- Agent 的 tool_calls 调用循环
- 工具相关测试

系统托盘已简化为：

- 显示
- 隐藏
- 退出

### 5. 使用文档更新

已更新：

- `AGENT_WORK_GUIDE.md`
- `PROGRESS.md`
- `DEVELOPMENT_LOG.md`

文档已改为描述当前精简版能力，不再把工具执行、权限分级、截图作为当前功能。

### 6. 测试与验证

当前核心测试结果：

```text
py -3.14 -m unittest desktop-agents.tests.test_agent_conversation desktop-agents.tests.test_agent_bus desktop-agents.tests.test_personality
Ran 12 tests
OK
```

应用已本地启动验证，桌面 Agent 能正常显示。

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
| 简化系统托盘 | 已完成 |
| 工具调用框架 | 已移除 |
| 文件读取工具 | 已移除 |
| 命令执行工具 | 已移除 |
| 截图工具 | 已移除 |
| 长期任务队列 | 未开始 |

## 下次可以继续的方向

1. **继续精简 UI**
   - 评估是否保留聊天记录窗口。
   - 评估是否保留导入聊天记录人格。
   - 简化右键菜单层级。

2. **收敛 1.0 范围**
   - 确认 1.0 只包含桌面聊天、人格切换、API Key 配置。
   - 跑完整手动验证。
   - 用户确认后再提交、打标签、推送。

3. **体验优化**
   - 减少默认 Agent 数量。
   - 优化气泡展示。
   - 调整自动群聊频率。

## 备注

- 当前版本不会主动读取文件、执行命令或截图。
- API Key fallback 到 QSettings 是为了解决当前 Windows 环境 keyring 后端不可用的问题。
- 项目不会主动下载 wx-mcp，只提供参考链接。
- 未经用户确认，不推送精简版到远程。
