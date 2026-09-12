import { describe, expect, it } from 'vitest'
import {
  completeChatAction,
  createChatAction,
  failRunningChatActions,
  finalizeChatStream,
  type ChatAction,
} from '@/lib/chatStream'

describe('chat stream actions', () => {
  it('matches out-of-order results for repeated tools by call id', () => {
    const actions = [
      createChatAction({ tool: 'search_questions', tool_call_id: 'call-1', input: { q: 'a' } }),
      createChatAction({ tool: 'search_questions', tool_call_id: 'call-2', input: { q: 'b' } }),
    ]

    expect(completeChatAction(actions, {
      tool: 'search_questions',
      tool_call_id: 'call-1',
      output: 'first',
    })).toBe(true)
    expect(actions[0]).toMatchObject({ status: 'completed', output: 'first' })
    expect(actions[1]).toMatchObject({ status: 'running' })
  })

  it('does not complete another action when an explicit call id is unknown', () => {
    const actions = [
      createChatAction({ tool: 'search_questions', tool_call_id: 'call-1', input: {} }),
    ]

    expect(completeChatAction(actions, {
      tool: 'search_questions',
      tool_call_id: 'missing',
      output: 'wrong',
    })).toBe(false)
    expect(actions[0].status).toBe('running')
  })

  it('falls back to the latest running action for legacy payloads', () => {
    const actions: ChatAction[] = [
      { tool: 'search_questions', input: { q: 'a' }, status: 'running' },
      { tool: 'search_questions', input: { q: 'b' }, status: 'running' },
    ]

    completeChatAction(actions, { tool: 'search_questions', output: 'legacy' })

    expect(actions[0].status).toBe('running')
    expect(actions[1]).toMatchObject({ status: 'completed', output: 'legacy' })
  })

  it('marks only unfinished actions as errors after an interrupted stream', () => {
    const actions: ChatAction[] = [
      { tool: 'done', input: {}, status: 'completed' },
      { tool: 'pending', input: {}, status: 'running' },
    ]

    failRunningChatActions(actions)

    expect(actions[0].status).toBe('completed')
    expect(actions[1]).toMatchObject({
      status: 'error',
      output: '连接提前中断，未收到工具执行结果',
    })
  })

  it('distinguishes an explicit done event from transport EOF', () => {
    const completedActions: ChatAction[] = [
      { tool: 'pending', input: {}, status: 'running' },
    ]
    expect(finalizeChatStream(completedActions, true)).toBe(true)
    expect(completedActions[0].status).toBe('running')

    const interruptedActions: ChatAction[] = [
      { tool: 'pending', input: {}, status: 'running' },
    ]
    expect(finalizeChatStream(interruptedActions, false)).toBe(false)
    expect(interruptedActions[0].status).toBe('error')
  })
})