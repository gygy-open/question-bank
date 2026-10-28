import { describe, expect, it } from 'vitest'
import { buildMcpSnippets, MCP_KEY_PLACEHOLDER, needsAllowHttp } from '../mcpClientConfig'

describe('mcpClientConfig', () => {
  it('uses the placeholder when no key is given', () => {
    const s = buildMcpSnippets('https://qb.example.com/api/mcp')
    expect(s.claudeCode).toBe(
      `claude mcp add --transport http questionbank https://qb.example.com/api/mcp --header "Authorization: Bearer ${MCP_KEY_PLACEHOLDER}"`,
    )
    expect(JSON.parse(s.cursor).mcpServers.questionbank).toEqual({
      url: 'https://qb.example.com/api/mcp',
      headers: { Authorization: `Bearer ${MCP_KEY_PLACEHOLDER}` },
    })
  })

  it('embeds a real key and VS Code server shape', () => {
    const s = buildMcpSnippets('http://127.0.0.1:8000/api/mcp', 'qb_abc')
    expect(JSON.parse(s.vscode).servers.questionbank).toEqual({
      type: 'http',
      url: 'http://127.0.0.1:8000/api/mcp',
      headers: { Authorization: 'Bearer qb_abc' },
    })
  })

  it('passes the header to mcp-remote via env and allows LAN http', () => {
    const lan = JSON.parse(buildMcpSnippets('http://192.168.1.5:8000/api/mcp', 'qb_abc').stdio).mcpServers.questionbank
    expect(lan.args).toEqual([
      '-y', 'mcp-remote', 'http://192.168.1.5:8000/api/mcp',
      '--header', 'Authorization:${AUTH_HEADER}', '--allow-http',
    ])
    expect(lan.env).toEqual({ AUTH_HEADER: 'Bearer qb_abc' })

    const local = JSON.parse(buildMcpSnippets('http://localhost:8000/api/mcp').stdio).mcpServers.questionbank
    expect(local.args).not.toContain('--allow-http')
  })

  it('builds a WorkBuddy streamableHttp config', () => {
    const wb = JSON.parse(buildMcpSnippets('http://192.168.1.5:8000/api/mcp', 'qb_abc').workbuddy).mcpServers.questionbank
    expect(wb).toEqual({
      type: 'streamableHttp',
      url: 'http://192.168.1.5:8000/api/mcp',
      headers: { Authorization: 'Bearer qb_abc' },
      description: 'QuestionBank',
    })
  })

  it('detects when --allow-http is needed', () => {
    expect(needsAllowHttp('https://qb.example.com/api/mcp')).toBe(false)
    expect(needsAllowHttp('http://127.0.0.1:8000/api/mcp')).toBe(false)
    expect(needsAllowHttp('http://questionbank.local:8000/api/mcp')).toBe(true)
    expect(needsAllowHttp('not a url')).toBe(false)
  })
})
