# 本地开发

面向贡献者的本地开发环境搭建。

## 前置要求

- Python 3.13+（通过 [uv](https://github.com/astral-sh/uv) 管理）
- Node.js 20+ 与 [pnpm](https://pnpm.io/)
- MySQL 8.0（或用 Docker 启动）
- Docker & Docker Compose（可选，一键起依赖）

## 后端

```bash
cd backend

# 安装依赖
uv sync

# 应用数据库迁移
uv run alembic upgrade head

# 初始化基础数据 / 创建超管(按需)
uv run python scripts/initial_data.py
uv run python scripts/create_superuser.py

# 启动开发服务器(热重载)
uv run fastapi dev app/main.py
```

后端默认监听 `http://localhost:8000`，API 文档在 `/docs`。

## 前端

```bash
cd frontend

# 安装依赖
pnpm install

# 启动开发服务器(将 /api 代理到后端)
pnpm dev
```

前端开发服务器会把 `/api` 代理到后端，无需额外跨域配置。

## 文档站（本仓库）

```bash
cd docs
pnpm install
pnpm docs:dev
```

## 常用命令

| 场景 | 命令 |
|------|------|
| 新增后端依赖 | `uv add <package>` |
| 生成迁移 | `uv run alembic revision --autogenerate -m "msg"` |
| 应用迁移 | `uv run alembic upgrade head` |
| 运行脚本 | `uv run python scripts/<script>.py` |
| 构建前端（桌面打包用） | `pnpm generate` |

更多约定见 [后端约定](/development/backend) 与 [前端约定](/development/frontend)。
