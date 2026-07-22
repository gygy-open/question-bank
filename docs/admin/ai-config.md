# AI 供应商与模型

AI 相关配置（供应商、模型、API Key）**存储在数据库中**，通过界面管理，可**热切换**、无需重启。此页功能为**超级管理员专属**。

## 供应商（Provider）

一个供应商代表一个 AI 服务来源。字段：

| 字段 | 说明 |
|------|------|
| 名称 | 显示名（如「官方 OpenAI」） |
| 接口类型 | `openai` 或 `gemini`（兼容 OpenAI 的服务选 `openai`） |
| Base URL | 自定义 API 地址|
| API Key | 密钥 |
| 是否启用 | 开关 |

支持 Gemini、OpenAI，以及所有 **OpenAI 兼容 API**（DeepSeek、通义、私有部署等）。

## 模型（Model）

每个供应商下可配置多个模型。字段：

| 字段 | 说明 |
|------|------|
| 名称 | 模型标识（如 `gpt-4o`、`gemini-pro`） |
| 支持视觉 | `is_vision_capable`，可处理图片输入 |
| 用于向量 | `is_embedding_model`，用作 Embedding 向量化 |

## 激活模型

系统区分三类「激活模型」，分别对应不同功能：

| 用途 | 系统参数键 | 影响功能 |
|------|-----------|---------|
| 文本 | `AI_TEXT_MODEL_ID` | [AI 对话](/features/chat)、文本类导入抽取 |
| 视觉 | `AI_VISION_MODEL_ID` | 图片识别导入、含图对话 |
| 向量 | `AI_EMBEDDING_MODEL_ID` | [知识点 RAG](/features/knowledge-points) |

在界面中为每类选择对应模型并保存，即刻生效。

::: tip 建议配置
- **文本模型**：用于抽取与对话，建议选能力较强的通用模型。
- **视觉模型**：图片导入必需，需勾选「支持视觉」。
- **Embedding 模型**：知识点检索必需，需勾选「用于向量」。
:::

## 安全提示

- API Key 属敏感信息，请妥善保管，避免泄露。
- 更换 Embedding 模型后，知识点会按新模型重新向量化。
