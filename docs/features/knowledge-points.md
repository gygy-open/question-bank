# 知识点体系

知识点体系是按学科组织的**树形知识结构**，用于给题目打上知识点标签，并支撑 AI 的知识点推荐（RAG）。

## 结构

- **树形**：通过 `parent_id` 建立父子层级，可多级嵌套。
- **按学科**：每个知识点属于某个学科。
- **唯一标识**：`(subject_id, slug)` 组合唯一，slug 为 URL 友好标识。

字段：名称 `name`、标识 `slug`、父节点 `parent_id`、所属学科 `subject_id`、创建 / 更新人。

## 管理操作

- 查看某学科的完整知识点树
- 新建根节点或子节点
- 重命名 / 修改 slug
- 删除（级联删除子节点）

::: warning 级联删除
删除一个知识点会**连带删除其所有子节点**，请谨慎操作。
:::

## 与题目关联

题目与知识点是**多对多**关系，可在题目上关联一个或多个知识点，并用知识点作为题库筛选条件。

## 向量化与 RAG

知识点会被**向量化写入 ChromaDB**，用于语义检索：

- 在 [AI 对话](/features/chat) 中，AI 可检索相关知识点 / 题目作为上下文。
- 智能导入时，AI 可将推荐的知识点映射到你的标准体系。

当在 [系统参数](/admin/system-settings) 中更新 **Embedding 模型**（`AI_EMBEDDING_MODEL_ID`）后，知识点会按新模型重新向量化。

::: tip 需要 Embedding 模型
RAG 依赖 Embedding 模型。请在 [AI 供应商与模型](/admin/ai-config) 中添加并激活一个用于向量化的模型。
:::

## 批量导入 / 同步

仓库提供脚本用于批量导入 / 同步知识点（开发 / 部署侧）：

- `scripts/import_math_knowledge_points.py`
- `scripts/sync_knowledge_points.py`

服务器版可通过 `docker compose exec backend uv run python scripts/<脚本名>.py` 运行。
