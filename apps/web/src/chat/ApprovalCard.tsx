import clsx from 'clsx'
import { motion } from 'framer-motion'
import { useState } from 'react'
import { CheckIcon, CloseIcon, WarningIcon } from '../components/ui/icons'
import { Button } from '../components/ui/primitives'
import { spring } from '../lib/motion'
import type { ApprovalAction, Decision } from './model'
import { JsonBlock } from './ToolChip'

interface SplitLine {
  name: string
  owes: { display: string }
}

function splitLines(details: Record<string, unknown> | null): SplitLine[] {
  const expense = (details as { expense?: { split?: SplitLine[] } } | null)?.expense
  return expense?.split ?? []
}

/**
 * The human-in-the-loop gate, as UI. The graph is paused on the host until the user
 * picks Approve / Edit / Reject; the choice is sent back as a LangGraph resume value.
 */
export function ApprovalCard({
  actions,
  decisions,
  onDecide,
  disabled,
}: {
  actions: ApprovalAction[]
  decisions?: Record<string, Decision>
  onDecide: (d: Record<string, Decision>) => void
  disabled?: boolean
}) {
  const [draft, setDraft] = useState<Record<string, Decision>>({})
  const [editing, setEditing] = useState<string | null>(null)
  const [feedback, setFeedback] = useState('')
  const resolved = decisions ?? null

  function choose(id: string, d: Decision) {
    const next = { ...draft, [id]: d }
    setDraft(next)
    setEditing(null)
    setFeedback('')
    if (actions.every((a) => next[a.tool_call_id])) onDecide(next)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={spring}
      role="group"
      aria-label="Action needs your approval"
      className="overflow-hidden rounded-[18px] border border-[var(--material-border)] bg-surface shadow-2"
    >
      {actions.map((a) => {
        const decided = resolved?.[a.tool_call_id] ?? draft[a.tool_call_id]
        const lines = splitLines(a.details)
        return (
          <div key={a.tool_call_id} className="border-b border-separator p-4 last:border-b-0">
            <div className="mb-1.5 flex items-center gap-2">
              <span
                className={clsx(
                  'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide',
                  a.destructive ? 'bg-negative-soft text-negative' : 'bg-accent-soft text-accent',
                )}
              >
                {a.destructive && <WarningIcon size={12} />}
                {a.destructive ? 'Destructive' : 'Needs approval'}
              </span>
              <span className="text-[13px] text-label-2">{a.title}</span>
            </div>
            <p className="text-[15px] font-medium leading-snug">{a.preview}</p>
            {lines.length > 0 && (
              <ul className="mt-2.5 space-y-1 rounded-[12px] bg-fill px-3 py-2 text-[14px]">
                {lines.map((l) => (
                  <li key={l.name} className="flex justify-between">
                    <span>{l.name}</span>
                    <span className="tabular text-label-2">{l.owes.display}</span>
                  </li>
                ))}
              </ul>
            )}
            <details className="mt-2 text-[13px] text-label-2">
              <summary className="cursor-pointer select-none hover:text-label">Tool call: {a.tool}</summary>
              <JsonBlock value={a.args} />
            </details>

            {decided ? (
              <p
                className={clsx(
                  'mt-3 flex items-center gap-1.5 text-[14px] font-medium',
                  decided.action === 'approve' ? 'text-positive' : 'text-label-2',
                )}
              >
                {decided.action === 'approve' ? <CheckIcon size={16} /> : <CloseIcon size={16} />}
                {decided.action === 'approve' ? 'Approved' : decided.action === 'reject' ? 'Rejected' : `Asked for changes: “${decided.feedback}”`}
              </p>
            ) : editing === a.tool_call_id ? (
              <form
                className="mt-3 space-y-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  if (feedback.trim()) choose(a.tool_call_id, { action: 'edit', feedback: feedback.trim() })
                }}
              >
                <label htmlFor={`fb-${a.tool_call_id}`} className="sr-only">
                  What should change?
                </label>
                <input
                  id={`fb-${a.tool_call_id}`}
                  autoFocus
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  placeholder="e.g. make it ₹1,500 and leave Rahul out"
                  className="h-10 w-full rounded-[10px] bg-fill px-3 text-[15px] focus:outline-none focus:ring-2 focus:ring-accent"
                />
                <div className="flex gap-2">
                  <Button type="button" size="sm" variant="secondary" onClick={() => setEditing(null)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" disabled={!feedback.trim()}>
                    Send changes
                  </Button>
                </div>
              </form>
            ) : (
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  variant={a.destructive ? 'destructive' : 'primary'}
                  disabled={disabled}
                  onClick={() => choose(a.tool_call_id, { action: 'approve' })}
                  className="flex-1"
                >
                  {a.destructive ? 'Delete' : 'Approve'}
                </Button>
                <Button size="sm" variant="secondary" disabled={disabled} onClick={() => setEditing(a.tool_call_id)}>
                  Edit
                </Button>
                <Button size="sm" variant="secondary" disabled={disabled} onClick={() => choose(a.tool_call_id, { action: 'reject' })}>
                  Reject
                </Button>
              </div>
            )}
          </div>
        )
      })}
    </motion.div>
  )
}
