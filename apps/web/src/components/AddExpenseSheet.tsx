import clsx from 'clsx'
import { useMemo, useState, type FormEvent } from 'react'
import { formatMoney, toMinor } from '../lib/money'
import { useAddExpense, useFriends, useGroup, useGroups } from '../lib/queries'
import { useAuth } from '../lib/stores'
import { CATEGORIES, type SplitType, type User } from '../lib/types'
import { useUI } from '../lib/ui'
import { categoryEmoji } from '../lib/display'
import { previewSplit } from '../lib/split'
import { Avatar, Button, ErrorNote, SegmentedControl, SelectField, TextField } from './ui/primitives'
import { Sheet } from './ui/Sheet'

const SPLITS: { value: SplitType; label: string }[] = [
  { value: 'equal', label: 'Equally' },
  { value: 'exact', label: 'Exact' },
  { value: 'percent', label: '%' },
  { value: 'shares', label: 'Shares' },
]

type Target = `g:${number}` | `f:${number}` | ''

type AddCtx = ReturnType<typeof useUI.getState>['addExpense']

export function AddExpenseSheet() {
  const { addExpense: ctx, closeAll } = useUI()
  return <AddExpenseForm key={ctx.nonce ?? 0} ctx={ctx} onClose={closeAll} />
}

function AddExpenseForm({ ctx, onClose }: { ctx: AddCtx; onClose: () => void }) {
  const me = useAuth((s) => s.user)
  const groups = useGroups()
  const friends = useFriends()

  // State starts from the context the sheet was opened with (the component remounts per open).
  const [chosen, setTarget] = useState<Target>(ctx.groupId ? `g:${ctx.groupId}` : ctx.friendId ? `f:${ctx.friendId}` : '')
  const [description, setDescription] = useState('')
  const [amountText, setAmountText] = useState('')
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [category, setCategory] = useState('general')
  const [payerId, setPayerId] = useState<number | null>(me?.id ?? null)
  const [splitType, setSplitType] = useState<SplitType>('equal')
  const [included, setIncluded] = useState<Record<number, boolean>>({})
  const [values, setValues] = useState<Record<number, string>>({})
  const add = useAddExpense()

  const target: Target = chosen || (groups.data?.[0] ? `g:${groups.data[0].id}` : '')
  const groupId = target.startsWith('g:') ? Number(target.slice(2)) : 0
  const friendId = target.startsWith('f:') ? Number(target.slice(2)) : 0
  const group = useGroup(groupId)
  const currency = groupId ? (group.data?.currency ?? 'INR') : 'INR'

  const people: User[] = useMemo(() => {
    if (groupId) return group.data?.members ?? []
    const f = friends.data?.find((x) => x.id === friendId)
    return me && f ? [me, f] : []
  }, [groupId, friendId, group.data, friends.data, me])

  const total = toMinor(amountText, currency) ?? 0
  const isIn = (id: number) => included[id] ?? true
  const active = people.filter((p) => isIn(p.id))
  const num = (id: number, fallback: number) => {
    const v = parseFloat(values[id] ?? '')
    return Number.isFinite(v) ? v : fallback
  }

  // Live per-person amounts + a validation message for the current split type.
  const { owed, problem } = useMemo(() => {
    const owedMap: Record<number, number> = {}
    let problem: string | null = null
    if (splitType === 'equal') {
      previewSplit(total, active.map(() => 1)).forEach((v, i) => (owedMap[active[i].id] = v))
      if (!active.length) problem = 'Choose at least one person.'
    } else if (splitType === 'exact') {
      let sum = 0
      for (const p of active) {
        const m = values[p.id] ? (toMinor(values[p.id], currency) ?? 0) : 0
        owedMap[p.id] = m
        sum += m
      }
      if (total && sum !== total)
        problem = sum < total ? `${formatMoney(total - sum, currency)} left to assign` : `${formatMoney(sum - total, currency)} over the total`
    } else {
      const weights = active.map((p) => num(p.id, splitType === 'shares' ? 1 : 0))
      previewSplit(total, weights).forEach((v, i) => (owedMap[active[i].id] = v))
      if (splitType === 'percent') {
        const pct = Math.round(weights.reduce((a, b) => a + b, 0) * 100) / 100
        if (pct !== 100) problem = `Percentages add up to ${pct}%, not 100%`
      }
    }
    return { owed: owedMap, problem }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [splitType, total, values, included, people, currency])

  const canSubmit = !!target && description.trim() && total > 0 && payerId && active.length > 0 && !problem

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit || !payerId) return
    add.mutate(
      {
        group_id: groupId || null,
        friend_id: friendId || null,
        description: description.trim(),
        amount: total,
        date,
        category,
        payer_id: payerId,
        split: {
          type: splitType,
          participants: active.map((p) => ({
            user_id: p.id,
            value:
              splitType === 'equal'
                ? null
                : splitType === 'exact'
                  ? (toMinor(values[p.id] ?? '', currency) ?? 0)
                  : String(num(p.id, splitType === 'shares' ? 1 : 0)),
          })),
        },
      },
      { onSuccess: onClose },
    )
  }

  return (
    <Sheet
      open={ctx.open}
      onClose={onClose}
      title="Add expense"
      footer={
        <Button type="submit" form="add-expense" size="lg" className="w-full" disabled={!canSubmit} loading={add.isPending}>
          Save {total > 0 ? formatMoney(total, currency) : 'expense'}
        </Button>
      }
    >
      <form id="add-expense" onSubmit={submit} className="space-y-4 p-4">
        <SelectField label="With" value={target} onChange={(e) => setTarget(e.target.value as Target)}>
          <option value="" disabled>
            Choose a group or friend
          </option>
          <optgroup label="Groups">
            {groups.data?.map((g) => (
              <option key={g.id} value={`g:${g.id}`}>
                {g.name}
              </option>
            ))}
          </optgroup>
          <optgroup label="Friends (no group)">
            {friends.data?.map((f) => (
              <option key={f.id} value={`f:${f.id}`}>
                {f.name}
              </option>
            ))}
          </optgroup>
        </SelectField>

        <TextField label="Description" placeholder="Dinner at Thalassa" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={200} required />

        <div className="grid grid-cols-[1.4fr_1fr] gap-3">
          <TextField
            label={`Amount (${currency})`}
            inputMode="decimal"
            placeholder="0.00"
            value={amountText}
            onChange={(e) => setAmountText(e.target.value)}
            className="[&_input]:tabular [&_input]:text-[22px] [&_input]:font-semibold"
            required
          />
          <TextField label="Date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <SelectField label="Paid by" value={payerId ?? ''} onChange={(e) => setPayerId(Number(e.target.value))}>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id === me?.id ? 'You' : p.name}
              </option>
            ))}
          </SelectField>
          <SelectField label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {categoryEmoji(c)} {c[0].toUpperCase() + c.slice(1)}
              </option>
            ))}
          </SelectField>
        </div>

        <div>
          <p className="mb-1.5 px-1 text-[13px] font-medium text-label-2">Split</p>
          <SegmentedControl label="Split type" options={SPLITS} value={splitType} onChange={setSplitType} />
        </div>

        <ul className="overflow-hidden rounded-[var(--radius-card)] bg-surface shadow-1">
          {people.map((p) => {
            const on = isIn(p.id)
            return (
              <li key={p.id} className="flex items-center gap-3 px-4 py-2.5 [&:not(:last-child)]:border-b [&:not(:last-child)]:border-separator">
                <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3">
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={(e) => setIncluded({ ...included, [p.id]: e.target.checked })}
                    className="h-5 w-5 rounded-full accent-[var(--accent)]"
                  />
                  <Avatar name={p.name} size={30} />
                  <span className={clsx('truncate', !on && 'text-label-3')}>{p.id === me?.id ? 'You' : p.name}</span>
                </label>
                {on && splitType !== 'equal' && (
                  <input
                    aria-label={`${splitType} for ${p.name}`}
                    inputMode="decimal"
                    placeholder={splitType === 'shares' ? '1' : splitType === 'percent' ? '0%' : '0.00'}
                    value={values[p.id] ?? ''}
                    onChange={(e) => setValues({ ...values, [p.id]: e.target.value })}
                    className="tabular h-9 w-20 rounded-[10px] bg-fill px-2.5 text-right text-[15px] focus:outline-none focus:ring-2 focus:ring-accent"
                  />
                )}
                <span className="tabular w-24 text-right text-[15px] text-label-2">{on ? formatMoney(owed[p.id] ?? 0, currency) : '–'}</span>
              </li>
            )
          })}
          {!people.length && <li className="px-4 py-6 text-center text-[15px] text-label-2">Choose a group or friend first.</li>}
        </ul>
        {problem && total > 0 && (
          <p role="status" className="px-1 text-[14px] text-warning">
            {problem}
          </p>
        )}
        <ErrorNote error={add.error} />
      </form>
    </Sheet>
  )
}
