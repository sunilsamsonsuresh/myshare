import clsx from 'clsx'
import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import { CheckIcon, ChevronRight, CloseIcon, PlugIcon, ToolIcon } from '../components/ui/icons'
import { Spinner } from '../components/ui/primitives'
import { spring } from '../lib/motion'
import { toolLabel, type ChatItem } from './model'

export function JsonBlock({ value, label }: { value: unknown; label?: string }) {
  return (
    <div className="mt-1.5">
      {label && <p className="mb-0.5 text-[11px] font-semibold uppercase tracking-wide text-label-3">{label}</p>}
      <pre className="max-h-64 overflow-auto rounded-[10px] bg-fill p-2.5 font-mono text-[11.5px] leading-relaxed text-label">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}

type Tool = Extract<ChatItem, { kind: 'tool' }>
type Resource = Extract<ChatItem, { kind: 'resource' }>

/**
 * One MCP interaction, shown inline: "Checking balances… ✓".
 * Expand it to see the actual JSON-RPC request and response that crossed the wire.
 */
export function ToolChip({ item }: { item: Tool | Resource }) {
  const [open, setOpen] = useState(false)
  const isTool = item.kind === 'tool'
  const status = isTool ? item.status : 'ok'
  const label = isTool ? toolLabel(item.tool, item.phase, item.status) : `Read ${item.uri}`
  const method = isTool ? 'tools/call' : 'resources/read'

  return (
    <div className="text-[13px]">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className={clsx(
          'inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 transition-colors',
          status === 'error' ? 'border-negative/30 bg-negative-soft text-negative' : 'border-separator bg-surface text-label-2 hover:text-label',
        )}
      >
        {isTool ? <ToolIcon size={13} /> : <PlugIcon size={13} />}
        <span className="truncate">{label}</span>
        {status === 'running' ? (
          <Spinner small />
        ) : status === 'ok' ? (
          <CheckIcon size={14} className="text-positive" />
        ) : (
          <CloseIcon size={13} />
        )}
        <ChevronRight size={12} className={clsx('transition-transform', open && 'rotate-90')} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={spring}
            className="overflow-hidden"
          >
            <div className="mt-1.5 rounded-[14px] border border-separator bg-surface p-3">
              <p className="text-[12px] text-label-2">
                MCP <code className="font-mono text-label">{method}</code>
                {isTool && item.phase === 'preview' && ' (dry run for the approval card)'}
                {isTool && item.summary && <span className="mt-1 block text-label">{item.summary}</span>}
              </p>
              {item.request != null ? (
                <JsonBlock label="Request (host → server)" value={item.request} />
              ) : (
                isTool && item.args && <JsonBlock label="Arguments" value={item.args} />
              )}
              {item.response != null && <JsonBlock label="Response (server → host)" value={item.response} />}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
