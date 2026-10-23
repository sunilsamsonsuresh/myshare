import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { HOST_URL, request } from '../lib/api'
import { invalidateMoney } from '../lib/queries'
import { useAuth } from '../lib/stores'
import { addUserMessage, applyEvent, emptyChat, recordDecisions, type ChatItem, type ChatState, type Decision } from './model'
import { streamSSE, type SSEEvent } from './sse'

const newThreadId = () => `web-${crypto.randomUUID().slice(0, 8)}`

interface ChatStore extends ChatState {
  open: boolean
  threadId: string
  setOpen: (open: boolean) => void
  send: (text: string) => Promise<void>
  runPrompt: (name: string, args: Record<string, string>) => Promise<void>
  decide: (approvalId: string, decisions: Record<string, Decision>) => Promise<void>
  newChat: () => void
  loadHistory: () => Promise<void>
}

export const useChat = create<ChatStore>()(
  persist(
    (set, get) => {
      /** POST /chat and fold every SSE event into the transcript as it arrives. */
      async function turn(body: Record<string, unknown>) {
        const token = useAuth.getState().token
        const onEvent = (e: SSEEvent) => {
          set((s) => applyEvent(s, e))
          // A write succeeded through MCP: refresh every screen that shows money.
          if (e.event === 'tool_call_result' && e.data.is_write && e.data.status === 'ok') invalidateMoney()
        }
        try {
          await streamSSE(
            `${HOST_URL}/chat`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
              body: JSON.stringify({ thread_id: get().threadId, ...body }),
            },
            onEvent,
          )
        } catch (err) {
          onEvent({ event: 'error', data: { message: err instanceof Error ? err.message : String(err) } })
          onEvent({ event: 'done', data: {} })
        }
      }

      return {
        ...emptyChat,
        open: false,
        threadId: newThreadId(),
        setOpen: (open) => set({ open }),
        send: async (text) => {
          set((s) => addUserMessage(s, text))
          await turn({ message: text })
        },
        runPrompt: async (name, args) => {
          set({ streaming: true })
          await turn({ prompt: { name, arguments: args } })
        },
        decide: async (approvalId, decisions) => {
          set((s) => recordDecisions(s, approvalId, decisions))
          await turn({ resume: { decisions } })
        },
        newChat: () => set({ ...emptyChat, threadId: newThreadId() }),
        loadHistory: async () => {
          // Rebuild the transcript from the host's LangGraph checkpointer (survives reloads/restarts).
          try {
            const h = await request<{
              messages: { role: string; text?: string }[]
              pending_approval: { actions: never[] } | null
            }>(HOST_URL, `/threads/${get().threadId}`)
            const items: ChatItem[] = h.messages
              .filter((m) => (m.role === 'user' || m.role === 'assistant') && m.text)
              .map((m, i) =>
                m.role === 'user'
                  ? { kind: 'user', id: `h${i}`, text: m.text! }
                  : { kind: 'assistant', id: `h${i}`, text: m.text!, streaming: false },
              )
            if (h.pending_approval) items.push({ kind: 'approval', id: 'h-pending', actions: h.pending_approval.actions })
            set({ items, awaitingApproval: !!h.pending_approval, streaming: false })
          } catch {
            /* host offline: keep whatever we have */
          }
        },
      }
    },
    // Only the thread id is persisted; the transcript is reloaded from the host.
    { name: 'myshare-chat', partialize: (s) => ({ threadId: s.threadId }) },
  ),
)
