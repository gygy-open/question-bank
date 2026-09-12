export interface ChatAction {
  tool: string
  toolCallId?: string
  input: unknown
  output?: string
  status: 'running' | 'completed' | 'error'
}

interface ToolStartedData {
  tool: string
  tool_call_id?: string
  input: unknown
}

interface ToolFinishedData {
  tool: string
  tool_call_id?: string
  output?: string
}

export const createChatAction = (data: ToolStartedData): ChatAction => ({
  tool: data.tool,
  toolCallId: data.tool_call_id,
  input: data.input,
  status: 'running',
})

export const completeChatAction = (
  actions: ChatAction[],
  data: ToolFinishedData,
): boolean => {
  let action: ChatAction | undefined
  if (data.tool_call_id) {
    action = actions.find(candidate => candidate.toolCallId === data.tool_call_id)
  } else {
    action = [...actions]
      .reverse()
      .find(candidate => candidate.tool === data.tool && candidate.status === 'running')
  }

  if (!action) return false
  action.status = 'completed'
  action.output = data.output
  return true
}

export const failRunningChatActions = (
  actions: ChatAction[],
  output = '连接提前中断，未收到工具执行结果',
): void => {
  for (const action of actions) {
    if (action.status !== 'running') continue
    action.status = 'error'
    action.output = output
  }
}

export const finalizeChatStream = (
  actions: ChatAction[],
  receivedDone: boolean,
): boolean => {
  if (receivedDone) return true
  failRunningChatActions(actions)
  return false
}