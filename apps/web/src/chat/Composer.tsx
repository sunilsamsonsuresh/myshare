import clsx from 'clsx'
import { AnimatePresence, motion } from 'framer-motion'
import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { SendIcon } from '../components/ui/icons'
import { Button } from '../components/ui/primitives'
import { spring } from '../lib/motion'
import { useGroups } from '../lib/queries'
import { usePrompts, type McpPrompt } from './mcpQueries'

/** Fill in a prompt's arguments. group_id gets a picker; month gets a month input. */
function PromptArgs({ prompt, onRun, onCancel }: { prompt: McpPrompt; onRun: (args: Record<string, string>) => void; onCancel: () => void }) {
  const groups = useGroups()
  const [args, setArgs] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    for (const a of prompt.arguments ?? []) init[a.name] = a.name === 'month' ? new Date().toISOString().slice(0, 7) : ''
    return init
  })
  const ready = (prompt.arguments ?? []).every((a) => !a.required || args[a.name]?.trim())
  const field = 'h-9 w-full rounded-[10px] bg-fill px-2.5 text-[15px] focus:outline-none focus:ring-2 focus:ring-accent'
  return (
    <form
      className="space-y-2 rounded-[16px] border border-separator bg-surface p-3 shadow-1"
      onSubmit={(e) => {
        e.preventDefault()
        if (ready) onRun(args)
      }}
    >
      <p className="text-[14px]">
        <span className="font-mono font-semibold text-accent">/{prompt.name}</span>{' '}
        <span className="text-label-2">{prompt.description}</span>
      </p>
      {(prompt.arguments ?? []).map((a) => (
        <label key={a.name} className="block">
          <span className="mb-0.5 block text-[12px] font-medium text-label-2">
            {a.name}
            {a.description ? ` · ${a.description}` : ''}
          </span>
          {a.name === 'group_id' ? (
            <select className={field} value={args[a.name]} onChange={(e) => setArgs({ ...args, [a.name]: e.target.value })} autoFocus>
              <option value="">Choose a group…</option>
              {groups.data?.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              autoFocus
              type={a.name === 'month' ? 'month' : 'text'}
              className={field}
              value={args[a.name]}
              onChange={(e) => setArgs({ ...args, [a.name]: e.target.value })}
            />
          )}
        </label>
      ))}
      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" size="sm" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={!ready}>
          Run prompt
        </Button>
      </div>
    </form>
  )
}

export function Composer({
  disabled,
  hint,
  onSend,
  onPrompt,
}: {
  disabled: boolean
  hint?: string
  onSend: (text: string) => void
  onPrompt: (name: string, args: Record<string, string>) => void
}) {
  const [text, setText] = useState('')
  const [active, setActive] = useState(0)
  const [chosen, setChosen] = useState<McpPrompt | null>(null)
  const prompts = usePrompts()
  const area = useRef<HTMLTextAreaElement>(null)

  const slash = text.startsWith('/') && !text.includes(' ') ? text.slice(1).toLowerCase() : null
  const matches = slash === null ? [] : (prompts.data ?? []).filter((p) => p.name.toLowerCase().includes(slash))
  const menuOpen = matches.length > 0 && !chosen

  function pick(p: McpPrompt) {
    setText('')
    if (p.arguments?.length) setChosen(p)
    else onPrompt(p.name, {})
  }

  function submit(e?: FormEvent) {
    e?.preventDefault()
    const t = text.trim()
    if (!t || disabled) return
    if (menuOpen) return pick(matches[active])
    onSend(t)
    setText('')
    if (area.current) area.current.style.height = ''
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (menuOpen && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault()
      setActive((a) => (a + (e.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length)
    } else if (menuOpen && (e.key === 'Tab' || e.key === 'Enter')) {
      e.preventDefault()
      pick(matches[Math.min(active, matches.length - 1)])
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    } else if (e.key === 'Escape' && text) {
      e.stopPropagation()
      setText('')
    }
  }

  return (
    <div className="relative">
      <AnimatePresence>
        {menuOpen && (
          <motion.ul
            role="listbox"
            aria-label="Prompts from the MCP server"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            transition={spring}
            className="absolute inset-x-0 bottom-full mb-2 overflow-hidden rounded-[16px] border border-separator bg-raised p-1 shadow-2"
          >
            <li className="px-2.5 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-label-3">MCP prompts</li>
            {matches.map((p, i) => (
              <li key={p.name} role="option" aria-selected={i === active}>
                <button
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onClick={() => pick(p)}
                  className={clsx('w-full rounded-[10px] px-2.5 py-1.5 text-left', i === active && 'bg-accent-soft')}
                >
                  <span className="font-mono text-[14px] font-semibold text-accent">/{p.name}</span>
                  <span className="block truncate text-[13px] text-label-2">{p.description}</span>
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>

      {chosen ? (
        <PromptArgs
          prompt={chosen}
          onCancel={() => setChosen(null)}
          onRun={(args) => {
            setChosen(null)
            onPrompt(chosen.name, args)
          }}
        />
      ) : (
        <form onSubmit={submit} className="flex items-end gap-2 rounded-[22px] border border-separator bg-surface p-1.5 pl-3.5 shadow-1 focus-within:ring-2 focus-within:ring-accent">
          <label htmlFor="chat-input" className="sr-only">
            Message the MyShare assistant
          </label>
          <textarea
            id="chat-input"
            ref={area}
            rows={1}
            value={text}
            disabled={disabled}
            onChange={(e) => {
              setText(e.target.value)
              setActive(0)
              e.target.style.height = 'auto'
              e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`
            }}
            onKeyDown={onKeyDown}
            placeholder={hint ?? 'Ask anything, or type / for prompts'}
            className="h-[34px] max-h-[140px] flex-1 resize-none bg-transparent py-1.5 text-[15px] placeholder:text-label-3 focus:outline-none disabled:opacity-60"
          />
          <button
            type="submit"
            aria-label="Send"
            disabled={disabled || !text.trim()}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-white transition active:scale-95 disabled:opacity-30"
          >
            <SendIcon size={18} />
          </button>
        </form>
      )}
    </div>
  )
}
