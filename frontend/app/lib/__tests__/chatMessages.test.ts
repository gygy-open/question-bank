import { describe, expect, it } from 'vitest'
import { applyChatMessageMeta, nextChatMessageUiId, type HasBackendId } from '@/lib/chatMessages'

describe('nextChatMessageUiId', () => {
  it('produces unique ids across calls', () => {
    const ids = new Set(Array.from({ length: 200 }, () => nextChatMessageUiId()))
    expect(ids.size).toBe(200)
  })
})

describe('applyChatMessageMeta', () => {
  const mk = (role: string): HasBackendId & { uiId: string } => ({
    uiId: nextChatMessageUiId(),
    role,
  })

  it('attaches the assistant id to the last (streaming) message', () => {
    const user = mk('user')
    const assistant = mk('assistant')
    const messages = [user, assistant]

    expect(applyChatMessageMeta(messages, { role: 'assistant', id: 42 })).toBe(true)
    expect(assistant.id).toBe(42)
    expect(user.id).toBeUndefined()
  })

  it('attaches the user id to the turn before the streaming reply', () => {
    const user = mk('user')
    const assistant = mk('assistant')
    const messages = [user, assistant]

    expect(applyChatMessageMeta(messages, { role: 'user', id: 7 })).toBe(true)
    expect(user.id).toBe(7)
    expect(assistant.id).toBeUndefined()
  })

  it('preserves the stable uiId while assigning backend ids', () => {
    const user = mk('user')
    const assistant = mk('assistant')
    const originalUserUiId = user.uiId
    const originalAssistantUiId = assistant.uiId
    const messages = [user, assistant]

    applyChatMessageMeta(messages, { role: 'user', id: 7 })
    applyChatMessageMeta(messages, { role: 'assistant', id: 42 })

    expect(user.uiId).toBe(originalUserUiId)
    expect(assistant.uiId).toBe(originalAssistantUiId)
  })

  it('no-ops on an empty list', () => {
    expect(applyChatMessageMeta([], { role: 'assistant', id: 1 })).toBe(false)
  })

  it('ignores a user meta when there is no preceding user turn', () => {
    const only = mk('assistant')
    expect(applyChatMessageMeta([only], { role: 'user', id: 9 })).toBe(false)
    expect(only.id).toBeUndefined()
  })
})
