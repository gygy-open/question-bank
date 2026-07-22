# 系统参数

系统参数是存于数据库的**动态业务配置**，可在运行时通过界面修改并即时生效。此页为**超级管理员专属**。

## 常用参数

| 键 | 说明 |
|----|------|
| `AI_TEXT_MODEL_ID` | 激活的对话 / 文本模型 |
| `AI_VISION_MODEL_ID` | 激活的视觉模型 |
| `AI_EMBEDDING_MODEL_ID` | 激活的向量嵌入模型 |
| `CHAT_SYSTEM_PROMPT` | 对话系统提示词（控制工具调用策略等） |
| `AI_EXTRACT_PROMPT` | 题目抽取提示词 |
| `AI_SOLVE_PROMPT` | 解答模式提示词 |

每个参数含键、值与描述。模型类参数通常在 [AI 供应商与模型](/admin/ai-config) 页面间接设置。

## 静态配置 vs 动态配置

| 类型 | 存储位置 | 修改方式 | 例子 |
|------|---------|---------|------|
| 静态配置 | 环境变量 / `.env` | 改后重启 | `SECRET_KEY`、`DB_URL` |
| 动态配置 | 数据库（`system_setting`） | 界面热更新 | 激活模型、系统 Prompt |

服务器版的静态配置见 [配置参考](/server/configuration)。

