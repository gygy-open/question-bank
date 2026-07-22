# AI 对话

AI 对话提供基于会话的多模型聊天，支持图片输入、Provider / Model 切换，并可调用题库工具。

## 会话与消息

- **会话（Session）**：每个对话是一个独立会话，含标题、创建 / 更新时间。
- **消息（Message）**：角色包括 `user` / `assistant` / `system` / `tool`。
- 会话与消息**持久化存储**，可随时回看历史。

## 多模型

- 支持 OpenAI、Gemini、DeepSeek 及兼容 API（通过 [AI 供应商与模型](/admin/ai-config) 配置）。
- 可选择用于对话的**文本模型**；图片输入需要**视觉模型**。

激活模型由系统参数控制：

- `AI_TEXT_MODEL_ID` — 对话文本模型
- `AI_VISION_MODEL_ID` — 图像处理模型
- `AI_EMBEDDING_MODEL_ID` — 向量嵌入模型

## 图片输入

- 可在消息中附带图片，系统自动转为 data URI 传给模型（支持 png / jpeg / webp）。
- 需激活**视觉模型**。

## 工具调用（题库集成）

对话中，AI 可按需调用题库工具：

- `search_questions` — 检索题目
- `create_question_draft` — 创建题目草稿
- `create_questions_batch` — 批量创建题目

::: tip 按需触发
默认策略下，AI **仅在你明确要求时**才使用这些工具，避免误操作。该策略由系统 Prompt（`CHAT_SYSTEM_PROMPT`）控制，见 [系统参数](/admin/system-settings)。
:::

## 流式响应

回复以流式（SSE）返回，前端逐步渲染，长回答也能即时看到进度。

## 会话管理

- 新建会话
- 会话列表（分页）
- 查看某会话的完整消息
- 删除会话
