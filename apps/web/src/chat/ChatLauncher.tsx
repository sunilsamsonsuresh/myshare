import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { PlugIcon, PlusIcon, SparklesIcon } from '../components/ui/icons'
import { IconButton } from '../components/ui/primitives'
import { Sheet } from '../components/ui/Sheet'
import { spring } from '../lib/motion'
import { CapabilitiesDrawer } from './CapabilitiesDrawer'
import { ChatMessages } from './ChatMessages'
import { Composer } from './Composer'
import { useChat } from './store'

const SUGGESTIONS = [
  'Who owes me money?',
  'Add ₹1,800 for cab to Goa Trip, paid by me, split equally',
  "What's the simplest way to settle Goa Trip?",
  'Show my last 5 expenses',
]

/**
 * The user-facing side of the MCP host: a floating button that opens the assistant.
 * Desktop: a non-modal side panel (the app stays visible and updates live behind it).
 * Mobile: a bottom sheet.
 */
export function ChatLauncher() {
  const chat = useChat()
  const [showCaps, setShowCaps] = useState(false)
  const scroller = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (chat.open && chat.items.length === 0) chat.loadHistory()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat.open])

  // Keep the newest message in view while streaming.
  useEffect(() => {
    const el = scroller.current?.closest('main')
    el?.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [chat.items])

  const busy = chat.streaming
  const hint = chat.awaitingApproval ? 'Approve or reject the action above first' : busy ? 'Working…' : undefined

  return (
    <>
      <AnimatePresence>
        {!chat.open && (
          <motion.button
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.6, opacity: 0 }}
            transition={spring}
            whileTap={{ scale: 0.92 }}
            onClick={() => chat.setOpen(true)}
            aria-label="Open the MyShare assistant"
            className="fixed bottom-[calc(76px+env(safe-area-inset-bottom))] right-4 z-40 flex h-14 items-center gap-2 rounded-full bg-accent pl-4 pr-5 text-[15px] font-semibold text-white shadow-3 md:bottom-6 md:right-6"
          >
            <SparklesIcon size={22} />
            Ask MyShare
          </motion.button>
        )}
      </AnimatePresence>

      <Sheet
        open={chat.open}
        onClose={() => chat.setOpen(false)}
        side="right"
        modal={false}
        initialFocus="none"
        title={
          <span className="flex items-center gap-2">
            <SparklesIcon size={18} className="text-accent" /> Assistant
          </span>
        }
        headerExtra={
          <>
            <IconButton label="Connected capabilities (MCP)" className="h-8 w-8" onClick={() => setShowCaps(true)}>
              <PlugIcon size={16} />
            </IconButton>
            <IconButton label="New chat" className="h-8 w-8" onClick={chat.newChat} disabled={busy}>
              <PlusIcon size={16} />
            </IconButton>
          </>
        }
        footer={
          <Composer
            disabled={busy || chat.awaitingApproval}
            hint={hint}
            onSend={chat.send}
            onPrompt={chat.runPrompt}
          />
        }
      >
        <div ref={scroller} className="px-4 py-4" role="log" aria-live="polite" aria-relevant="additions" aria-busy={busy}>
          {chat.items.length === 0 ? (
            <div className="pt-6 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-[14px] bg-accent-soft text-accent">
                <SparklesIcon size={26} />
              </div>
              <p className="text-[17px] font-semibold">Ask about your expenses</p>
              <p className="mx-auto mt-1 max-w-[280px] text-[14px] text-label-2">
                I use the MyShare MCP server. Reads happen instantly; changes wait for your approval.
              </p>
              <div className="mt-5 flex flex-col gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => chat.send(s)}
                    className="rounded-[14px] border border-separator bg-surface px-3.5 py-2.5 text-left text-[14px] transition hover:bg-fill"
                  >
                    {s}
                  </button>
                ))}
                <p className="mt-1 text-[13px] text-label-3">
                  Tip: type <kbd className="font-mono">/</kbd> for prompts
                </p>
              </div>
            </div>
          ) : (
            <ChatMessages items={chat.items} streaming={busy} onDecide={chat.decide} />
          )}
          {busy && chat.items[chat.items.length - 1]?.kind === 'user' && (
            <p className="mt-3 animate-pulse text-[13px] text-label-2">Thinking…</p>
          )}
        </div>
      </Sheet>
      <CapabilitiesDrawer open={showCaps} onClose={() => setShowCaps(false)} />
    </>
  )
}
