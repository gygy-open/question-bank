# 数据库与迁移

Question Bank 支持两种数据库，通过统一的数据模型与 Alembic 迁移保持兼容：

- **SQLite**:桌面版默认，零配置，单文件。
- **MySQL 8.0**:服务器版默认，面向团队与生产。

## 迁移（Alembic）

数据库结构变更通过 [Alembic](https://alembic.sqlalchemy.org/) 管理。迁移脚本位于 `backend/alembic/versions/`。

服务器版容器启动时通常会自动应用迁移；手动执行：

```bash
# 应用到最新版本
docker compose exec backend uv run alembic upgrade head

# 查看当前版本
docker compose exec backend uv run alembic current
```

开发环境（非容器）下：

```bash
cd backend
uv run alembic upgrade head
```

新增迁移（改了模型后）：

```bash
uv run alembic revision --autogenerate -m "描述本次变更"
uv run alembic upgrade head
```

::: tip 双库基线
仓库当前采用「双库基线」迁移（SQLite / MySQL 通用）。历史 MySQL 专用迁移归档在 `backend/alembic/versions_archive_mysql/`，一般无需关注。
:::

## 备份与恢复（服务器版 / MySQL）

**备份：**

```bash
# 导出 MySQL 数据
docker compose exec mysql mysqldump -u root -p question_bank > backup.sql

# 同时备份向量库与上传文件
tar czf data-backup.tgz chromadb_data backend/uploads backend/static
```

**恢复：**

```bash
# 恢复 MySQL
docker compose exec -T mysql mysql -u root -p question_bank < backup.sql

# 恢复数据文件(解压覆盖)
tar xzf data-backup.tgz
```

## 备份（桌面版 / SQLite）

关闭桌面应用后，直接复制数据目录：

```
%APPDATA%\QuestionBank
```

详见 [个人使用 · 备份与恢复](/desktop/personal#备份与恢复)。

## 从桌面版迁移到服务器版

桌面版与服务器版共用同一套模型，但底层数据库不同（SQLite → MySQL），迁移思路：

1. **数据量小 / 结构一致**：在服务器版中重新 [智能导入](/features/import) 原始文件，或手动补录。
2. **需要完整迁移**：导出 SQLite 数据并转换写入 MySQL（结构由 Alembic 保证一致）。

::: warning 迁移前务必备份
任何迁移操作前，请先分别备份桌面版数据目录与服务器版数据库。
:::
