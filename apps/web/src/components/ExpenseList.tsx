import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import { formatMoney } from '../lib/money'
import { useDeleteExpense } from '../lib/queries'
import { useAuth } from '../lib/stores'
import type { Activity, Expense } from '../lib/types'
import { categoryEmoji, listItemSeparator, timeAgo } from '../lib/display'
import { spring } from '../lib/motion'
import { TrashIcon } from './ui/icons'
import { Amount, Avatar, Button, EmojiTile, ErrorNote, Row } from './ui/primitives'
import { Sheet } from './ui/Sheet'

const monthFmt = new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' })
const dayFmt = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' })
const parseDay = (d: string) => new Date(`${d}T12:00:00`)

/** Expenses grouped by month, as inset grouped lists, with animated insert/remove. */
export function ExpenseList({ expenses, showGroup = false }: { expenses: Expense[]; showGroup?: boolean }) {
  const [selected, setSelected] = useState<Expense | null>(null)
  const months = new Map<string, Expense[]>()
  for (const e of expenses) {
    const k = monthFmt.format(parseDay(e.date))
    months.set(k, [...(months.get(k) ?? []), e])
  }
  return (
    <>
      {[...months].map(([month, items]) => (
        <section key={month} className="mb-6">
          <h3 className="mb-1.5 px-4 text-[13px] font-medium uppercase tracking-wide text-label-2">{month}</h3>
          <ul className="overflow-hidden rounded-[var(--radius-card)] bg-surface shadow-1">
            <AnimatePresence initial={false}>
              {items.map((e) => (
                <motion.li
                  key={e.id}
                  layout
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={spring}
                  className={listItemSeparator}
                >
                  <ExpenseRow e={e} showGroup={showGroup} onClick={() => setSelected(e)} />
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        </section>
      ))}
      <ExpenseDetail expense={selected} onClose={() => setSelected(null)} />
    </>
  )
}

function ExpenseRow({ e, showGroup, onClick }: { e: Expense; showGroup: boolean; onClick: () => void }) {
  const me = useAuth((s) => s.user)
  const payer = e.payer.id === me?.id ? 'You' : e.payer.name.split(' ')[0]
  return (
    <Row
      onClick={onClick}
      chevron={false}
      leading={<EmojiTile emoji={categoryEmoji(e.category)} />}
      title={e.description}
      subtitle={`${dayFmt.format(parseDay(e.date))} · ${payer} paid ${formatMoney(e.amount, e.currency)}${showGroup && e.group_name ? ` · ${e.group_name}` : ''}`}
      trailing={
        e.my_net === 0 ? (
          <span className="text-[13px] text-label-2">not involved</span>
        ) : (
          <div className="leading-tight">
            <div className={e.my_net > 0 ? 'text-[12px] text-positive' : 'text-[12px] text-negative'}>
              {e.my_net > 0 ? 'you lent' : 'you borrowed'}
            </div>
            <Amount minor={e.my_net} currency={e.currency} className="text-[15px] font-semibold" />
          </div>
        )
      }
    />
  )
}

function ExpenseDetail({ expense, onClose }: { expense: Expense | null; onClose: () => void }) {
  const me = useAuth((s) => s.user)
  const del = useDeleteExpense()
  const [confirming, setConfirming] = useState(false)
  const close = () => {
    setConfirming(false)
    del.reset()
    onClose()
  }
  const e = expense
  return (
    <Sheet open={!!e} onClose={close} title={e?.description ?? ''}>
      {e && (
        <div className="space-y-5 p-4">
          <div className="flex items-center gap-4">
            <EmojiTile emoji={categoryEmoji(e.category)} size={56} />
            <div>
              <div className="tabular text-[28px] font-bold">{formatMoney(e.amount, e.currency)}</div>
              <div className="text-[14px] text-label-2">
                {parseDay(e.date).toLocaleDateString(undefined, { dateStyle: 'long' })}
                {e.group_name ? ` · ${e.group_name}` : ''} · {e.split_type} split
              </div>
            </div>
          </div>
          <ul className="overflow-hidden rounded-[var(--radius-card)] bg-surface shadow-1">
            {e.splits.map((s) => (
              <li key={s.user.id} className={listItemSeparator}>
                <Row
                  leading={<Avatar name={s.user.name} size={34} />}
                  title={s.user.id === me?.id ? 'You' : s.user.name}
                  subtitle={s.user.id === e.payer.id ? `paid ${formatMoney(e.amount, e.currency)}` : undefined}
                  trailing={
                    <span className="tabular text-[15px]">
                      owes {formatMoney(s.owed_amount, e.currency)}
                      {s.share_value && e.split_type !== 'exact' && (
                        <span className="text-label-2"> ({s.share_value}{e.split_type === 'percent' ? '%' : 'x'})</span>
                      )}
                    </span>
                  }
                />
              </li>
            ))}
          </ul>
          <ErrorNote error={del.error} />
          {confirming ? (
            <div className="flex gap-2">
              <Button variant="secondary" className="flex-1" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
              <Button variant="destructive" className="flex-1" loading={del.isPending} onClick={() => del.mutate(e.id, { onSuccess: close })}>
                Delete for everyone
              </Button>
            </div>
          ) : (
            <Button variant="destructive" className="w-full" icon={<TrashIcon size={18} />} onClick={() => setConfirming(true)}>
              Delete expense
            </Button>
          )}
        </div>
      )}
    </Sheet>
  )
}

const VERB_EMOJI: Record<string, string> = {
  expense_added: '🧾',
  expense_updated: '✏️',
  expense_deleted: '🗑️',
  settlement_added: '🤝',
  group_created: '✨',
  group_deleted: '🗑️',
  member_added: '👋',
  member_removed: '🚪',
  friend_added: '🫶',
}

export function ActivityRow({ a }: { a: Activity }) {
  return (
    <Row
      leading={<EmojiTile emoji={VERB_EMOJI[a.verb] ?? '•'} size={36} />}
      title={<span className="whitespace-normal text-[15px] leading-snug">{a.summary}</span>}
      subtitle={timeAgo(a.created_at)}
    />
  )
}
