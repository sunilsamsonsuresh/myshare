import { useMemo, useState, type FormEvent } from 'react'
import { formatMoney, toDecimalString, toMinor } from '../lib/money'
import { useFriends, useGroup, useSettle } from '../lib/queries'
import { useAuth } from '../lib/stores'
import type { User } from '../lib/types'
import { useUI } from '../lib/ui'
import { ArrowRight } from './ui/icons'
import { Avatar, Button, ErrorNote, SelectField, TextField } from './ui/primitives'
import { Sheet } from './ui/Sheet'

type SettleCtx = ReturnType<typeof useUI.getState>['settle']

/** Record a payment between two people (optionally inside a group). */
export function SettleSheet() {
  const { settle: ctx, closeAll } = useUI()
  return <SettleForm key={ctx.nonce ?? 0} ctx={ctx} onClose={closeAll} />
}

function SettleForm({ ctx, onClose }: { ctx: SettleCtx; onClose: () => void }) {
  const me = useAuth((s) => s.user)
  const friends = useFriends()
  const group = useGroup(ctx.groupId ?? 0)
  const [fromId, setFromId] = useState(ctx.fromUserId ?? me?.id ?? 0)
  const [toId, setToId] = useState(ctx.toUserId ?? 0)
  const [amountText, setAmountText] = useState(ctx.amount ? toDecimalString(ctx.amount) : '')
  const [note, setNote] = useState('')
  const settle = useSettle()
  const currency = group.data?.currency ?? 'INR'

  const people: User[] = useMemo(() => {
    if (ctx.groupId) return group.data?.members ?? []
    return me ? [me, ...(friends.data ?? [])] : []
  }, [ctx.groupId, group.data, friends.data, me])

  const amount = toMinor(amountText, currency) ?? 0
  const from = people.find((p) => p.id === fromId)
  const to = people.find((p) => p.id === toId)
  const valid = from && to && from.id !== to.id && amount > 0
  const name = (u?: User) => (u ? (u.id === me?.id ? 'You' : u.name.split(' ')[0]) : '?')

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!valid) return
    settle.mutate(
      { from_user_id: fromId, to_user_id: toId, amount, group_id: ctx.groupId ?? null, note: note || undefined },
      { onSuccess: onClose },
    )
  }

  return (
    <Sheet
      open={ctx.open}
      onClose={onClose}
      title={ctx.groupId && group.data ? `Settle up · ${group.data.name}` : 'Record a payment'}
      footer={
        <Button type="submit" form="settle" size="lg" className="w-full" disabled={!valid} loading={settle.isPending}>
          Record {amount > 0 ? formatMoney(amount, currency) : 'payment'}
        </Button>
      }
    >
      <form id="settle" onSubmit={submit} className="space-y-4 p-4">
        <div className="flex items-center justify-center gap-4 py-3" aria-hidden>
          <div className="flex w-24 flex-col items-center gap-1.5">
            {from ? <Avatar name={from.name} size={52} /> : <div className="h-[52px] w-[52px] rounded-full bg-fill" />}
            <span className="truncate text-[14px] font-medium">{name(from)}</span>
          </div>
          <ArrowRight className="text-label-3" size={26} />
          <div className="flex w-24 flex-col items-center gap-1.5">
            {to ? <Avatar name={to.name} size={52} /> : <div className="h-[52px] w-[52px] rounded-full bg-fill" />}
            <span className="truncate text-[14px] font-medium">{name(to)}</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <SelectField label="Who paid" value={fromId} onChange={(e) => setFromId(Number(e.target.value))}>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id === me?.id ? 'You' : p.name}
              </option>
            ))}
          </SelectField>
          <SelectField label="Who received" value={toId} onChange={(e) => setToId(Number(e.target.value))}>
            <option value={0} disabled>
              Choose…
            </option>
            {people
              .filter((p) => p.id !== fromId)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.id === me?.id ? 'You' : p.name}
                </option>
              ))}
          </SelectField>
        </div>
        <TextField
          label={`Amount (${currency})`}
          inputMode="decimal"
          placeholder="0.00"
          value={amountText}
          onChange={(e) => setAmountText(e.target.value)}
          className="[&_input]:tabular [&_input]:text-[22px] [&_input]:font-semibold"
        />
        <TextField label="Note (optional)" placeholder="UPI, cash…" value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
        <p className="px-1 text-[13px] text-label-2">This only records the payment in MyShare; no money is moved.</p>
        <ErrorNote error={settle.error} />
      </form>
    </Sheet>
  )
}
