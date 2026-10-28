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

镜像已通过 CI 自动构建并发布到 GitHub Container Registry（`ghcr.io/gygy-open/question-bank-backend`、`ghcr.io/gygy-open/question-bank-frontend`），推荐直接拉取，无需在服务器上本地构建。`docker-compose.yml` 中 `backend` / `worker` / `frontend` 均已配置好对应的 `image:`，默认拉取 `latest`。

## 部署步骤

```bash
# 1. 只需 docker-compose.yml 与 .env.example 两个文件即可，无需克隆完整仓库
curl -O https://raw.githubusercontent.com/gygy-open/question-bank/main/docker-compose.yml
curl -O https://raw.githubusercontent.com/gygy-open/question-bank/main/.env.example
cp .env.example .env
```

编辑 `.env`，**至少**设置以下项（完整清单见 [配置参考](/server/configuration)）：

- `SECRET_KEY` — JWT 签名密钥，请用随机值：`openssl rand -hex 32`
- `MYSQL_ROOT_PASSWORD` — MySQL root 密码
- `MYSQL_PASSWORD` — 应用数据库用户密码

```bash
# 2. 拉取镜像并启动全部服务
docker compose pull
docker compose up -d
```

3. 浏览器打开题库，首次访问会进入初始化向导，直接创建首个超级管理员（数据库已由 `DB_URL` 配置，无需再选）。

   也可以改用命令行（创建 `admin` / `password`，登录后请立即修改密码）：

   ```bash
   docker compose exec backend python scripts/create_superuser.py
   ```

::: warning
首个打开页面的人即可创建超级管理员。部署完成后请尽快完成初始化。
:::

::: tip 想本地构建 / 二次开发？
克隆完整仓库后，把 `.env` 中的 `IMAGE_TAG` 留空或忽略，改用 `docker compose up -d --build` 即可基于本地源码构建镜像（`docker-compose.yml` 同时声明了 `image` 与 `build`，加 `--build` 会本地构建并覆盖同名 tag）。适合贡献者或需要自定义 Dockerfile 的场景。
:::

## 中国大陆加速

CI 在发布到 GHCR 的同时会把**同一份镜像**推到阿里云容器镜像服务（ACR，杭州），tag 与国际版完全一致；mysql / chromadb 也已同步一份。仓库均为公开，无需 `docker login`。

在部署步骤基础上只多一条命令 —— 把加速配置下载成 `docker-compose.override.yml`，Compose 会自动加载它：

```bash
curl -o docker-compose.override.yml \
  https://raw.githubusercontent.com/gygy-open/question-bank/main/docker-compose.cn.yml

docker compose pull
docker compose up -d
```

不需要额外环境变量，也不需要给命令加 `-f`，后续所有 `docker compose ...` 命令与文档完全一致。想恢复成从 GHCR 拉取，删掉 `docker-compose.override.yml` 即可。

::: tip 想保留原文件名？
下载为 `docker-compose.cn.yml` 也可以，但每条命令都要显式带上两个文件：

```bash
docker compose -f docker-compose.yml -f docker-compose.cn.yml up -d
```
:::

## 访问

- 前端：`http://<服务器IP>`（默认 80 端口）
- 后端 API 文档（Swagger）：`http://<服务器IP>:8000/docs`
- MCP 服务：`http://<服务器IP>/api/mcp`，经前端 nginx 转发到后端，见 [MCP 接入](/features/mcp)

## 首次配置

登录后，以超级管理员身份：

1. 首次登录会自动进入引导页，创建第一个学科（题库以学科为单位组织）。
2. 在 [AI 供应商与模型](/admin/ai-config) 中添加 Provider / Model 并设为激活。
3. 在 [用户与权限](/admin/users) 中为团队成员创建账号。
4. 开始 [智能导入](/features/import) 或手动录题。

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

# 更新到新版本（拉取最新镜像）
docker compose pull
docker compose up -d
```

默认使用 `latest` 标签（对应 `main` 分支最新构建）。如需锁定到具体版本，在 `.env` 中设置 `IMAGE_TAG`（如 `1.2.0`），再执行 `docker compose pull && docker compose up -d`。可用标签见 [容器包页面](https://github.com/gygy-open/question-bank/pkgs/container/question-bank-backend)。

### 试用测试版（与正式版并存）

测试版会把数据升级到新格式且不可回退，请不要直接把正式部署的 `IMAGE_TAG` 改成测试版。另建一套独立部署，数据复制过去即可：

1. 新建目录（如 `question-bank-alpha`），复制 `docker-compose.yml`、`.env`（及 `docker-compose.override.yml`，如有）。
2. 在新目录的 `.env` 中设置：
   ```bash
   COMPOSE_PROJECT_NAME=question-bank-alpha   # 独立的容器与数据卷
   IMAGE_TAG=1.5.0-alpha.1                    # 测试版标签
   HTTP_PORT=8080                             # 与正式版同时运行
   ```
3. 把正式版数据复制到新数据卷（复制期间先停止正式版，保证 MySQL 数据一致）：
   ```bash
   (cd 正式版目录 && docker compose stop)
   for v in mysql_data app_data chromadb_data; do
     docker run --rm -v question-bank_$v:/from -v question-bank-alpha_$v:/to alpine cp -a /from/. /to/
   done
   (cd 正式版目录 && docker compose start)
   ```
4. 在新目录执行 `docker compose up -d`，访问 `http://服务器:8080`。测试版只会升级这份副本。

不再需要时，在新目录执行 `docker compose down -v` 即可删除测试版及其数据卷，正式版不受影响。

更多见 [运维](/server/operations) 与 [数据库与迁移](/server/database)。

## 数据持久化

- **MySQL 数据**：命名卷 `mysql_data`。
- **向量数据**：命名卷 `chromadb_data`。
- **上传文件 / 静态资源**：命名卷 `app_data`，挂载到后端容器的 `/data`（对应 `DATA_DIR`），内含 `uploads/` 与 `static/media/`。

后端容器以 root 启动 entrypoint，将 `/data` 的属主修正为容器内的 `nonroot`（uid 999）后再降权运行，因此使用命名卷或宿主目录绑定挂载都不会出现权限问题。

备份时需一并覆盖上述数据，详见 [数据库与迁移](/server/database)。

### 从旧版本升级（数据卷合并）

旧版本使用 `uploads_data:/app/uploads` 与 `static_data:/app/static` 两个卷。升级后改为单个 `app_data:/data`，需要搬运一次（`question-bank_` 是 Compose 项目名前缀）：

```bash
docker compose down
docker volume create question-bank_app_data
docker run --rm \
  -v question-bank_static_data:/old/static \
  -v question-bank_uploads_data:/old/uploads \
  -v question-bank_app_data:/data \
  alpine sh -c 'mkdir -p /data/static /data/uploads \
    && cp -a /old/static/. /data/static/ \
    && cp -a /old/uploads/. /data/uploads/'
docker compose pull
docker compose up -d
```

确认图片与上传文件正常后，再删除旧卷：

```bash
docker volume rm question-bank_static_data question-bank_uploads_data
```
