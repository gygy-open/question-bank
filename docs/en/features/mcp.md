# MCP Access

QuestionBank ships with a built-in [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server. Once connected, MCP-capable AI clients such as Claude, Cursor and VS Code can search questions, add questions, review, and build papers **on your behalf**.

## How it works

- **One address**: MCP shares the port with the web app and always lives at `<your URL>/api/mcp`, for both the desktop and the Docker editions.
- **Per-user API keys**: every user creates keys under "Settings → MCP access". A key has **exactly the same permissions** as the account that created it; subject member roles, question visibility and all other rules still apply.
- **Transport**: Streamable HTTP (stateless). Clients authenticate with an `Authorization: Bearer <API key>` header.

## Create an API key

1. Open "Settings → MCP access".
2. Click "Create API key" and give it a recognizable name (e.g. "Claude on office PC").
3. **Copy the full key right away.** Only the prefix is kept after you close the window; the key can't be shown again.
4. "Revoke" keys you no longer use. Revoked keys stop working immediately.

::: warning Keep it secret
An API key can change or delete anything you are allowed to. Never commit it to a repository or share it. Each user can have at most 20 keys.
:::

## Configure your client

"Settings → MCP access" generates ready-to-copy snippets for each client based on the address you are using. Replace the URL and key in the examples below with your own.

**Claude Code**:

```bash
claude mcp add --transport http questionbank https://qb.example.com/api/mcp --header "Authorization: Bearer <YOUR_API_KEY>"
```

**Cursor** (`~/.cursor/mcp.json`):

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

**VS Code** (workspace `.vscode/mcp.json`):

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

**WorkBuddy**: add the following to its MCP configuration, save it, then enable the server in the connector list.

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

**Clients that only support local commands (stdio)**, such as Claude Desktop: bridge through [mcp-remote](https://www.npmjs.com/package/mcp-remote), which requires Node.js. If the address is a LAN `http://` URL, also add the `--allow-http` argument.

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

::: tip Desktop edition address
By default the desktop edition only listens on this computer, so the address looks like `http://127.0.0.1:8000/api/mcp` (the port moves up if 8000 is taken; use the one shown in Settings). To connect clients on other computers, turn on [LAN sharing](/en/desktop/lan-sharing) first and use the LAN address shown in Settings.
:::

## Available tools

| Category | Tools |
|------|------|
| Query | `list_subjects`, `search_questions`, `get_question`, `check_question_duplicates`, `list_knowledge_points`, `list_tags`, `list_composition_folders`, `list_compositions`, `get_composition` |
| Media | `create_media_upload_url` |
| Knowledge points & tags | `knowledge_point_create`, `tag_create` (require editor permission in the subject) |
| Questions | `question_create`, `question_update`, `question_review`, `question_delete`, `question_batch_create`, `question_batch_update`, `question_batch_confirm`, `question_batch_delete`, `question_derived_create`, `question_relation_create`, `question_relation_delete` |
| Compositions | `composition_create`, `composition_write_nodes`, `composition_update`, `composition_replace_nodes`, `composition_sync_question_nodes`, `composition_sync_question_group_nodes`, `composition_delete`, `composition_restore`, `composition_duplicate`, `composition_finalize_version`, `composition_create_folder`, `composition_update_folder`, `composition_delete_folder` |

Tips:

- Most tools need a `subject_id`; call `list_subjects` first.
- `scope_type` for composition tools: `shared` is shared with the subject team, `personal` is visible only to you. Personal compositions always belong to the key's owner and can't be assigned to anyone else.
- Changing a composition requires `expected_revision` (optimistic locking); read the latest value with `get_composition` first.
- Recommended flow for building a paper: create it with `composition_create`, then add simple nodes (headings, Markdown text, question IDs, etc.) with `composition_write_nodes`; the server builds the internal structure. It appends by default (`mode: append`); `mode: replace` discards the existing content. `composition_replace_nodes` is a low-level tool that rewrites the node tree directly and is rarely needed.
- New questions are drafts and still go through the [review workflow](/en/features/review-workflow) before publishing.
- Creating questions runs the [duplicate check](/en/features/questions#duplicate-check): when a duplicate or highly similar question exists, the tool returns `question.duplicate_suspected` with the candidates, and the AI should ask you before retrying with `allow_duplicate: true`. Use `check_question_duplicates` to check in advance.
- To add images (or audio) to questions, see [Uploading images and audio](#uploading-images-and-audio) below.
- Delete tools carry the `destructiveHint` annotation, so most clients ask for confirmation before running them.

## Uploading images and audio

Images in questions must first be uploaded to the subject's media library; the question then references the asset ID (`assetId`). Because tool arguments are generated token by token by the model, they are not suitable for carrying file contents, so uploading takes two steps:

1. The AI calls `create_media_upload_url` (argument `subject_id`) and receives an upload URL **valid for 10 minutes**.
2. The AI runs `curl -sS -F 'file=@plot.png' '<upload URL>'` locally. The `node` in the response can be put straight into rich-text content such as the question stem:

```json
{ "type": "image", "attrs": { "src": "/api/v1/media/42/content", "assetId": 42 } }
```

Notes:

- The client must be able to run local commands (e.g. Claude Code, Cursor, WorkBuddy). Clients that can only call tools cannot upload; let the AI create the question first and add the image in the web app.
- The upload URL is only a short-lived delegation of the API key: it requires edit permission on the subject, and every upload re-checks that the key has not been revoked, the user is still active and MCP is enabled.
- Accepted formats: PNG, JPEG, GIF and WebP images (up to 10 MB each) and MP3, M4A, OGG and WAV audio. SVG is not accepted for security reasons; export charts to PNG first.
- An uploaded asset can only be referenced by questions in the same subject.

## Administration and auditing

- **Admin switch**: administrators can turn off the whole MCP service in "Settings → MCP access". All keys stop working immediately and work again once it is turned back on.
- **Admin view**: administrators can see every user's keys (name, prefix, created and last-used time) and revoke them, but cannot see the key values.
- **Automatic invalidation**: revoking a key, or deactivating or deleting a user, makes the affected keys unusable immediately.
- **Auditing**: every write made through MCP (including failed attempts) is recorded in the [Activity Logs](/en/features/activity-logs) as "MCP call", with the tool name and key prefix. Read-only queries are not logged.

## Security notes

- Keys are stored only as hashes and can only be sent in the `Authorization` header.
- Browser requests that carry an `Origin` header must be same-origin, which stops other web pages from calling the server cross-site. If you really need access from another web page (e.g. an online MCP inspector), the operator can allow it via `MCP_ALLOWED_ORIGINS`; see [Environment variables](/en/server/configuration#runtime).
- When deploying on the public internet, enable HTTPS so keys are never sent in plain text.
