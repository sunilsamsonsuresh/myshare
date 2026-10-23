// The chat transcript as the UI sees it, and a pure reducer that applies host SSE events.
// Keeping this pure (no React, no fetch) makes the streaming logic easy to test.

export interface ApprovalAction {
  tool_call_id: string
  tool: string
  title: string
  args: Record<string, unknown>
  preview: string
  details: Record<string, unknown> | null
  destructive: boolean
}

export type Decision = { action: 'approve' | 'reject' | 'edit'; feedback?: string }

export type ChatItem =
  | { kind: 'user'; id: string; text: string }
  | { kind: 'assistant'; id: string; text: string; streaming: boolean }
  | {
      kind: 'tool'
      id: string
      tool: string
      phase: 'preview' | 'call'
      status: 'running' | 'ok' | 'error' | 'rejected' | 'changes_requested'
      args?: Record<string, unknown>
      summary?: string
      request?: unknown
      response?: unknown
    }
  | { kind: 'resource'; id: string; uri: string; request?: unknown; response?: unknown }
  | { kind: 'prompt'; id: string; name: string; text: string }
  | { kind: 'approval'; id: string; actions: ApprovalAction[]; decisions?: Record<string, Decision> }
  | { kind: 'error'; id: string; text: string }

export interface ChatState {
  items: ChatItem[]
  streaming: boolean
  awaitingApproval: boolean
}

export const emptyChat: ChatState = { items: [], streaming: false, awaitingApproval: false }

let counter = 0
const uid = (p: string) => `${p}-${Date.now().toString(36)}-${(counter++).toString(36)}`

type Ev = { event: string; data: Record<string, unknown> }

/** Apply one SSE event from the host to the transcript. */
export function applyEvent(state: ChatState, { event, data }: Ev): ChatState {
  const items = [...state.items]
  const last = items[items.length - 1]
  const toolKey = (d: Record<string, unknown>) => `${d.phase}:${d.id}`

  switch (event) {
    case 'token': {
      const text = String(data.text ?? '')
      if (last?.kind === 'assistant' && last.streaming) items[items.length - 1] = { ...last, text: last.text + text }
      else items.push({ kind: 'assistant', id: uid('a'), text, streaming: true })
      return { ...state, items }
    }
    case 'resource_read':
      items.push({ kind: 'resource', id: uid('r'), uri: String(data.uri), request: data.request, response: data.response })
      return { ...state, items: closeAssistant(items) }
    case 'prompt_loaded': {
      const msgs = (data.messages as { role: string; text: string }[]) ?? []
      const userText = msgs.filter((m) => m.role === 'user').map((m) => m.text).join('\n\n')
      if (userText) items.push({ kind: 'prompt', id: uid('p'), name: String(data.name), text: userText })
      return { ...state, items }
    }
    case 'tool_call_started':
      items.push({
        kind: 'tool',
        id: toolKey(data),
        tool: String(data.tool),
        phase: data.phase as 'preview' | 'call',
        status: 'running',
        args: data.args as Record<string, unknown>,
      })
      return { ...state, items: closeAssistant(items) }
    case 'tool_call_result': {
      const key = toolKey(data)
      const i = items.findIndex((x) => x.kind === 'tool' && x.id === key)
      const patch = {
        status: data.status as 'ok',
        summary: data.summary as string | undefined,
        request: data.request,
        response: data.response,
      }
      if (i >= 0) items[i] = { ...(items[i] as Extract<ChatItem, { kind: 'tool' }>), ...patch }
      else items.push({ kind: 'tool', id: key, tool: String(data.tool), phase: data.phase as 'call', ...patch })
      return { ...state, items: closeAssistant(items) }
    }
    case 'approval_required': {
      const actions = (data.actions as ApprovalAction[]) ?? []
      const ids = actions.map((a) => a.tool_call_id).join(',')
      const already = items.some((x) => x.kind === 'approval' && !x.decisions && x.actions.map((a) => a.tool_call_id).join(',') === ids)
      if (!already) items.push({ kind: 'approval', id: uid('ap'), actions })
      return { ...state, items: closeAssistant(items), awaitingApproval: true }
    }
    case 'error':
      items.push({ kind: 'error', id: uid('e'), text: String(data.message ?? 'Something went wrong') })
      return { ...state, items: closeAssistant(items) }
    case 'done':
      return { ...state, items: closeAssistant(items), streaming: false, awaitingApproval: !!data.awaiting_approval }
    default:
      return state
  }
}

function closeAssistant(items: ChatItem[]): ChatItem[] {
  return items.map((x) => (x.kind === 'assistant' && x.streaming ? { ...x, streaming: false } : x))
}

export function addUserMessage(state: ChatState, text: string): ChatState {
  return { ...state, streaming: true, items: [...state.items, { kind: 'user', id: uid('u'), text }] }
}

export function recordDecisions(state: ChatState, approvalId: string, decisions: Record<string, Decision>): ChatState {
  return {
    ...state,
    streaming: true,
    awaitingApproval: false,
    items: state.items.map((x) => (x.kind === 'approval' && x.id === approvalId ? { ...x, decisions } : x)),
  }
}

/** Friendly labels for tool activity chips: [while running, when done]. */
const TOOL_LABELS: Record<string, [string, string]> = {
  resolve_person: ['Finding person', 'Found person'],
  list_friends: ['Looking up friends', 'Looked up friends'],
  list_groups: ['Looking up groups', 'Looked up groups'],
  get_group_details: ['Opening group', 'Opened group'],
  get_balances: ['Checking balances', 'Checked balances'],
  list_expenses: ['Listing expenses', 'Listed expenses'],
  search_expenses: ['Searching expenses', 'Searched expenses'],
  get_simplified_debts: ['Simplifying debts', 'Simplified debts'],
  add_expense: ['Adding expense', 'Added expense'],
  update_expense: ['Updating expense', 'Updated expense'],
  delete_expense: ['Deleting expense', 'Deleted expense'],
  settle_up: ['Recording payment', 'Recorded payment'],
  create_group: ['Creating group', 'Created group'],
  add_friend: ['Adding friend', 'Added friend'],
}

export function toolLabel(tool: string, phase: 'preview' | 'call', status: string): string {
  if (phase === 'preview') return status === 'running' ? `Checking ${tool}…` : status === 'ok' ? `Prepared preview` : `Preview failed`
  const [running, done] = TOOL_LABELS[tool] ?? [`Running ${tool}`, `Ran ${tool}`]
  if (status === 'running') return `${running}…`
  if (status === 'rejected') return 'Rejected by you'
  if (status === 'changes_requested') return 'Changes requested'
  if (status === 'error') return `${running} failed`
  return done
}
