# MCP 接入

题库内置 [MCP（Model Context Protocol）](https://modelcontextprotocol.io) 服务。Claude、Cursor、VS Code 等支持 MCP 的 AI 客户端接入后，可以**以你的身份**检索题目、录题、审核、组卷。

## 工作方式

- **同一个地址**：MCP 与网页使用同一个端口，地址固定为 `<访问地址>/api/mcp`。桌面版、Docker 版都一样。
- **用户级 API Key**：每位用户在「设置 → MCP 接入」里自行创建 Key。Key 的权限**完全等同于**创建者账号，学科成员角色、题目可见性等规则全部照常生效。
- **传输方式**：Streamable HTTP（无状态）。客户端以 `Authorization: Bearer <API Key>` 请求头鉴权。

## 创建 API Key

1. 打开「设置 → MCP 接入」。
2. 点击「创建 API Key」，起一个便于辨认的名字（如“办公室电脑的 Claude”）。
3. 创建成功后**立即复制**完整的 Key。窗口关闭后系统只保留前缀，无法再次查看。
4. 不再使用的 Key 请及时「撤销」，撤销后立即失效。

::: warning 妥善保管
API Key 可以修改、删除你有权操作的任何内容。不要提交到代码仓库或分享给他人。每位用户最多 20 个 Key。
:::

## 配置客户端

「设置 → MCP 接入」页面会按当前访问地址生成各客户端的配置片段，复制即可使用。以下示例中的地址与 Key 请替换为你自己的。

**Claude Code**：

```bash
claude mcp add --transport http questionbank https://qb.example.com/api/mcp --header "Authorization: Bearer <YOUR_API_KEY>"
```

**Cursor**（`~/.cursor/mcp.json`）：

```json
{
  "mcpServers": {
    "questionbank": {
      "url": "https://qb.example.com/api/mcp",
      "headers": { "Authorization": "Bearer <YOUR_API_KEY>" }
    }
  }
}
```

**VS Code**（工作区 `.vscode/mcp.json`）：

```json
{
  "servers": {
    "questionbank": {
      "type": "http",
      "url": "https://qb.example.com/api/mcp",
      "headers": { "Authorization": "Bearer <YOUR_API_KEY>" }
    }
  }
}
```

**WorkBuddy**：在 MCP 配置中加入以下内容，保存后在连接器列表中启用。

```json
{
  "mcpServers": {
    "questionbank": {
      "type": "streamableHttp",
      "url": "https://qb.example.com/api/mcp",
      "headers": { "Authorization": "Bearer <YOUR_API_KEY>" },
      "description": "QuestionBank"
    }
  }
}
```

**只支持本地命令（stdio）的客户端**，如 Claude Desktop：借助 [mcp-remote](https://www.npmjs.com/package/mcp-remote) 桥接，需先安装 Node.js。地址是局域网内的 `http://` 时，需额外加上 `--allow-http` 参数。

```json
{
  "mcpServers": {
    "questionbank": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://qb.example.com/api/mcp", "--header", "Authorization:${AUTH_HEADER}"],
      "env": { "AUTH_HEADER": "Bearer <YOUR_API_KEY>" }
    }
  }
}
```

::: tip 桌面版的接入地址
桌面版默认只监听本机，地址形如 `http://127.0.0.1:8000/api/mcp`（端口被占用时会顺延，以设置页显示为准）。若要让其他电脑上的客户端接入，先开启 [局域网共享](/desktop/lan-sharing)，再使用设置页显示的局域网地址。
:::

## 可用工具

| 类别 | 工具 |
|------|------|
| 查询 | `list_subjects`、`search_questions`、`get_question`、`check_question_duplicates`、`list_knowledge_points`、`list_tags`、`list_composition_folders`、`list_compositions`、`get_composition` |
| 媒体 | `create_media_upload_url` |
| 知识点与标签 | `knowledge_point_create`、`tag_create`（需该学科的编辑权限） |
| 题目 | `question_create`、`question_update`、`question_review`、`question_delete`、`question_batch_create`、`question_batch_update`、`question_batch_confirm`、`question_batch_delete`、`question_derived_create`、`question_relation_create`、`question_relation_delete` |
| 组卷 | `composition_create`、`composition_write_nodes`、`composition_update`、`composition_replace_nodes`、`composition_sync_question_nodes`、`composition_sync_question_group_nodes`、`composition_delete`、`composition_restore`、`composition_duplicate`、`composition_finalize_version`、`composition_create_folder`、`composition_update_folder`、`composition_delete_folder` |

使用要点：

- 多数工具需要 `subject_id`，先调用 `list_subjects` 获取。
- 组卷工具的 `scope_type`：`shared` 为学科团队共享，`personal` 为仅自己可见。个人稿件的归属由 Key 所属用户决定，无法指定为他人。
- 修改稿件需要传入 `expected_revision`（乐观锁），先用 `get_composition` 读取最新值。
- 组卷推荐流程：`composition_create` 新建稿件，再用 `composition_write_nodes` 写入小标题、Markdown 正文和题目 ID 等简单节点，系统自动生成内部结构。默认追加到末尾（`mode: append`），`mode: replace` 会清空原有内容。`composition_replace_nodes` 是直接改写节点树的底层工具，一般不需要使用。
- 新建的题目默认是草稿，仍需按 [审核工作流](/features/review-workflow) 发布。
- 录题会自动[查重](/features/questions#录入查重)：命中重复或高度相似的题时工具返回 `question.duplicate_suspected` 和候选题，AI 应先向你确认，再带 `allow_duplicate: true` 重试。也可以先用 `check_question_duplicates` 预检。
- 题目要配图（或音频）时，见下文 [上传图片与音频](#上传图片与音频)。
- 删除类工具带有 `destructiveHint` 标记，多数客户端会在执行前请求确认。

## 上传图片与音频

题目里的图片必须先上传到所属学科的媒体库，拿到资产 ID（`assetId`）后才能引用。由于工具参数由模型逐字生成，不适合直接传输文件内容，上传分两步：

1. AI 调用 `create_media_upload_url`（参数 `subject_id`），得到一个 **10 分钟内有效**的上传地址。
2. AI 在本地执行 `curl -sS -F 'file=@plot.png' '<上传地址>'`，返回值里的 `node` 可直接放进题干等富文本内容：

```json
{ "type": "image", "attrs": { "src": "/api/v1/media/42/content", "assetId": 42 } }
```

说明：

- 需要客户端能执行本地命令（如 Claude Code、Cursor、WorkBuddy）。只能调用工具的客户端无法上传，可让 AI 先建题，再在网页上补图。
- 上传地址只是 API Key 的短时委托：需要对该学科有编辑权限；每次上传都会重新检查 Key 是否已撤销、用户是否已停用以及 MCP 是否开启。
- 支持 PNG、JPEG、GIF、WebP 图片（单张不超过 10 MB）和 MP3、M4A、OGG、WAV 音频。出于安全考虑不支持 SVG，图表请先导出为 PNG。
- 上传的资产只能被同一学科的题目引用。

## 管理与审计

- **管理员总开关**：管理员可在「设置 → MCP 接入」关闭整个 MCP 服务。关闭后所有 Key 立即失效，重新开启后恢复。
- **管理员视图**：管理员可查看所有用户的 Key（名称、前缀、创建与最近使用时间）并撤销，但看不到 Key 内容。
- **自动失效**：撤销 Key、停用或删除用户后，相关 Key 立即无法使用。
- **审计**：通过 MCP 执行的写操作（含失败的尝试）都会记入 [操作审计](/features/activity-logs)，行为为「MCP 调用」，并记录工具名与 Key 前缀。只读查询不记录。

## 安全说明

- Key 仅以哈希形式存储，只能通过 `Authorization` 请求头传递。
- 带 `Origin` 头的浏览器请求必须与站点同源，以防网页跨站调用。如确需从其他网页（如在线 MCP 调试工具）访问，由运维在 `MCP_ALLOWED_ORIGINS` 中放行，见 [环境变量](/server/configuration#运行时)。
- 在公网部署时请为站点启用 HTTPS，避免 Key 以明文在网络中传输。
