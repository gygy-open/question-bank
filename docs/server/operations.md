# 运维

面向服务器版（Docker Compose）日常运维的常用操作与排障。

## 服务管理

```bash
# 查看各服务状态
docker compose ps

# 启动 / 停止 / 重启
docker compose up -d
docker compose down
docker compose restart backend

# 重建(改了代码 / 配置后)
docker compose up -d --build
```

## 日志

```bash
# 实时查看
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend

# 最近 200 行
docker compose logs --tail=200 backend
```

日志级别由 `.env` 的 `LOG_LEVEL` 控制（默认 `INFO`），排障时可临时设为 `DEBUG` 并重建容器。

## 后台任务（Worker）

`worker` 服务处理异步任务（如导入）。若导入卡在「处理中」，优先检查 worker 日志：

```bash
docker compose logs -f worker
```

确保 worker 与 backend 使用相同的 `DB_URL` 与 `CHROMADB_HOST`（默认已在 `docker-compose.yml` 中对齐）。

## 升级

```bash
git pull
docker compose up -d --build
# 如有数据库结构变更
docker compose exec backend uv run alembic upgrade head
```

升级前建议先 [备份](/server/database#备份与恢复-服务器版-mysql)。

## 常见问题排查

| 现象 | 排查方向 |
|------|---------|
| 前端打不开 | `docker compose ps` 看 `frontend`/`backend` 是否 Up；查看 backend 日志 |
| 登录报错 / Token 失效 | 检查 `SECRET_KEY` 是否被改动（改动会使已签发 Token 失效） |
| AI 功能报错 | 检查 [AI 供应商与模型](/admin/ai-config) 配置与 API Key、网络连通性 |
| 知识点检索无结果 | 确认 `chromadb` 服务正常、已配置 Embedding 模型 |
| 导入不完成 | 查看 `worker` 日志；确认 AI 模型可用 |
| 数据库连接失败 | 确认 `mysql` 健康检查通过、密码与 `DB_URL` 一致 |


## 反向代理与 HTTPS（可选）

如需通过域名 / HTTPS 对外提供服务，可在前面加一层 Nginx / Caddy / Traefik 反向代理，将 80/443 转发到 `frontend`。请确保：

- 仅暴露必要端口；
- 配置 HTTPS 证书；
- 后端 `SECRET_KEY` 妥善保管。

::: warning 安全
将服务暴露到公网前，务必使用强密码、HTTPS，并限制来源。轻量内网协作可优先考虑桌面版 [局域网共享](/desktop/lan-sharing)。
:::
