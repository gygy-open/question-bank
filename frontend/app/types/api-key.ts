export interface ApiKey {
  id: number
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
}

export interface ApiKeyCreated extends ApiKey {
  key: string
}

export interface ApiKeyAdmin extends ApiKey {
  user_id: number
  username: string
  full_name: string | null
}

export interface McpInfo {
  enabled: boolean
  path: string
}
