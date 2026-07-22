# 配置参考

服务器版通过 `.env` 文件（被 `docker-compose.yml` 读取）进行配置。将 `.env.example` 复制为 `.env` 后按需修改。

::: warning 敏感信息
`.env` 包含密钥与密码，已被 `.gitignore` 排除，**切勿提交到仓库**。
:::

## 必填项

| 变量 | 说明 | 示例 / 生成方式 |
|------|------|----------------|
| `SECRET_KEY` | JWT 签名密钥，务必用长随机值 | `openssl rand -hex 32` |
| `MYSQL_ROOT_PASSWORD` | MySQL root 密码 | 自定义强密码 |
| `MYSQL_PASSWORD` | 应用数据库用户密码 | 自定义强密码 |

## 数据库相关

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MYSQL_DATABASE` | `question_bank` | 数据库名 |
| `MYSQL_USER` | `question_bank` | 应用数据库用户 |
| `DB_URL` | `mysql+aiomysql://question_bank:<MYSQL_PASSWORD>@mysql:3306/question_bank` | 后端连接串，通常无需手动设置 |

## 向量数据库（ChromaDB）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHROMADB_HOST` | `chromadb` | ChromaDB 主机（容器名） |
| `CHROMADB_PORT` | `8000` | 容器内端口 |

## 运行时

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | 日志级别（`DEBUG`/`INFO`/`WARNING`/`ERROR`） |
| `UID` / `GID` | `1000` | 容器内运行用户，避免挂载卷的权限问题 |

## AI 配置不在 .env 里

AI 供应商、模型、API Key 等**动态业务配置存储在数据库中**，通过界面管理，而非环境变量。登录后在 [AI 供应商与模型](/admin/ai-config) 配置，支持热切换。

同理，审核阈值、Prompt 模板等业务参数也在界面中管理，见 [系统参数](/admin/system-settings)。

::: tip 静态 vs 动态配置
- **静态配置**（启动前确定）：`.env` / 环境变量，如密钥、数据库连接。
- **动态配置**（运行时可改）：数据库中的 `system_setting` 等表，通过界面热更新。
:::

## 修改配置后

改动 `.env` 后需重建容器使其生效：

```bash
docker compose up -d
```
