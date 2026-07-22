# Docker Compose 部署

服务器版通过 Docker Compose 一键启动完整技术栈，适合团队与生产环境。整套服务包括：

| 服务 | 作用 | 端口（默认） |
|------|------|-----------|
| `mysql` | 主数据库（MySQL 8.0） | 3306 |
| `chromadb` | 向量数据库（知识点 RAG） | 8001 → 容器 8000 |
| `backend` | FastAPI 后端 API | 8000 |
| `worker` | 后台任务处理（导入等） | — |
| `frontend` | 前端（Nginx 提供 SPA） | 80 |

## 前置要求

- 一台安装了 **Docker** 与 **Docker Compose** 的服务器（Linux 推荐）
- 可访问的 AI 供应商（Gemini / OpenAI / 兼容 API）

## 部署步骤

```bash
# 1. 克隆仓库
git clone https://github.com/gygy-open/question-bank.git question-bank && cd question-bank

# 2. 生成环境变量文件
cp .env.example .env
```

编辑 `.env`，**至少**设置以下项（完整清单见 [配置参考](/server/configuration)）：

- `SECRET_KEY` — JWT 签名密钥，请用随机值：`openssl rand -hex 32`
- `MYSQL_ROOT_PASSWORD` — MySQL root 密码
- `MYSQL_PASSWORD` — 应用数据库用户密码

```bash
# 3. 启动全部服务
docker compose up -d --build

# 4. 首次启动后初始化基础数据
docker compose exec backend python scripts/initial_data.py

# 5. 创建超级管理员
docker compose exec backend python scripts/create_superuser.py
```

## 访问

- 前端：`http://<服务器IP>`（默认 80 端口）
- 后端 API 文档（Swagger）：`http://<服务器IP>:8000/docs`

## 首次配置

登录后，以超级管理员身份：

1. 在 [AI 供应商与模型](/admin/ai-config) 中添加 Provider / Model 并设为激活。
2. 在 [用户与权限](/admin/users) 中为团队成员创建账号。
3. 开始 [智能导入](/features/import) 或手动录题。

## 常用运维命令

```bash
# 查看运行状态
docker compose ps

# 查看日志
docker compose logs -f backend
docker compose logs -f worker

# 停止 / 启动
docker compose down
docker compose up -d

# 更新到新版本(拉取代码后)
git pull
docker compose up -d --build
```

更多见 [运维](/server/operations) 与 [数据库与迁移](/server/database)。

## 数据持久化

- **MySQL 数据**：命名卷 `mysql_data`（见 `docker-compose.yml`）。
- **向量数据**：`./chromadb_data`。
- **上传文件 / 静态资源**：`./backend/uploads`、`./backend/static`。

备份时需一并覆盖上述数据，详见 [数据库与迁移](/server/database)。
