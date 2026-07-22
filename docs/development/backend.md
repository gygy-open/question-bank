# 后端约定

后端为 Python 3.13 + FastAPI + SQLAlchemy（Async）。以下为主要约定，贡献代码请遵循。

## 异步优先

数据库操作**全部使用 `AsyncSession` 与 `await`**。

## SQLAlchemy 2.0 语法

```python
result = await db.execute(
    select(Question).where(Question.status == QuestionStatus.PUBLISHED)
)
questions = result.scalars().all()
```

## CRUD 模式

新增数据访问请继承 `app/crud/base.py:CRUDBase`：

```python
class CRUDQuestion(CRUDBase[Question, QuestionCreate, QuestionUpdate]):
    ...
```

## 类型注解

强制类型注解（`typing.List`、`typing.Optional` 等）。

## 依赖管理

使用 `uv`：

```bash
uv add <package>
```

## 数据库迁移

```bash
uv run alembic revision --autogenerate -m "描述"
uv run alembic upgrade head
```

迁移脚本位于 `backend/alembic/versions/`，当前采用 SQLite / MySQL 通用的双库基线。

## AI 集成

- 新增 AI 供应商：实现 `app/services/ai_provider.py` 的 `AIProvider` 接口。
- 文档解析 / 抽取：使用 `app/services/doc_processor.py` 的 `DocProcessor`。
- AI 配置是**数据库驱动**（`ai_providers`、`ai_models` 表），不是环境变量。

## 配置

- 静态配置：`app/core/config.py`。
- 动态业务配置：`system_setting` 表（界面热更新）。

## 目录速览

| 目录 | 职责 |
|------|------|
| `app/api/v1/endpoints/` | 路由端点 |
| `app/crud/` | 数据访问 |
| `app/models/` | ORM 模型 |
| `app/schemas/` | Pydantic 模型 |
| `app/services/` | 业务服务 |
| `scripts/` | 运维 / 数据脚本 |
