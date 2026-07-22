# Prompt 模板

Prompt 模板用于保存常用的提示词，便于在对话等场景中复用。

## 模板字段

| 字段 | 说明 |
|------|------|
| 标题 | 模板名称 |
| 内容 | 提示词正文 |
| 归属 | 按用户隔离（各自管理自己的模板） |

## 操作

- 新建 / 编辑 / 删除模板
- 在 [AI 对话](/features/chat) 等流程中调用

## 与系统 Prompt 的区别

- **Prompt 模板**：用户级、可复用的提示词片段。
- **系统 Prompt**（如 `CHAT_SYSTEM_PROMPT`、`AI_EXTRACT_PROMPT`、`AI_SOLVE_PROMPT`）：控制对话 / 抽取 / 解答的**全局行为**，在 [系统参数](/admin/system-settings) 中由管理员配置。
