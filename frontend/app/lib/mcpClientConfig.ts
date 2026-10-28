/** 各 MCP 客户端的接入配置片段(纯函数,便于单测)。 */

export const MCP_SERVER_NAME = 'questionbank'
export const MCP_KEY_PLACEHOLDER = '<YOUR_API_KEY>'

export type McpSnippetId = 'claudeCode' | 'cursor' | 'vscode' | 'workbuddy' | 'stdio'

/** mcp-remote 默认拒绝非 localhost 的 http 地址,需要显式 --allow-http */
export function needsAllowHttp(url: string): boolean {
  try {
    const u = new URL(url)
    return u.protocol === 'http:' && !['localhost', '127.0.0.1', '[::1]'].includes(u.hostname)
  } catch {
    return false
  }
}

const json = (value: unknown) => JSON.stringify(value, null, 2)

/**
 * 经 mcp-remote 把远程 HTTP 服务桥接成本地 stdio 命令。
 * 请求头经环境变量传入:Windows 下 args 里带空格的值容易被拆开。
 */
function mcpRemoteCommand(url: string, auth: string) {
  return {
    command: 'npx',
    args: [
      '-y', 'mcp-remote', url,
      '--header', 'Authorization:${AUTH_HEADER}',
      ...(needsAllowHttp(url) ? ['--allow-http'] : []),
    ],
    env: { AUTH_HEADER: auth },
  }
}

export function buildMcpSnippets(url: string, apiKey?: string): Record<McpSnippetId, string> {
  const auth = `Bearer ${apiKey || MCP_KEY_PLACEHOLDER}`
  return {
    claudeCode: `claude mcp add --transport http ${MCP_SERVER_NAME} ${url} --header "Authorization: ${auth}"`,
    cursor: json({
      mcpServers: { [MCP_SERVER_NAME]: { url, headers: { Authorization: auth } } },
    }),
    vscode: json({
      servers: { [MCP_SERVER_NAME]: { type: 'http', url, headers: { Authorization: auth } } },
    }),
    workbuddy: json({
      mcpServers: {
        [MCP_SERVER_NAME]: {
          type: 'streamableHttp',
          url,
          headers: { Authorization: auth },
          description: 'QuestionBank',
        },
      },
    }),
    stdio: json({
      mcpServers: { [MCP_SERVER_NAME]: mcpRemoteCommand(url, auth) },
    }),
  }
}
