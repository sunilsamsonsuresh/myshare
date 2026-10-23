import { AnimatePresence, motion } from 'framer-motion'
import { useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router'
import { ActivityRow, ExpenseList } from '../components/ExpenseList'
import { ArrowRight, PlusIcon, TrashIcon } from '../components/ui/icons'
import { kindEmoji, listItemSeparator } from '../lib/display'
import { Page } from '../components/ui/Page'
import {
  Amount,
  Avatar,
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Row,
  Section,
  SegmentedControl,
  Skeleton,
  TextField,
} from '../components/ui/primitives'
import { useActivity, useAddMember, useDeleteGroup, useExpenses, useGroup, useSimplified } from '../lib/queries'
import { formatMoney } from '../lib/money'
import { useAuth } from '../lib/stores'
import { useUI } from '../lib/ui'

type Tab = 'expenses' | 'balances' | 'settle' | 'activity'

export function GroupDetail() {
  const id = Number(useParams().id)
  const group = useGroup(id)
  const [tab, setTab] = useState<Tab>('expenses')
  const { openAddExpense } = useUI()
  const g = group.data

  if (group.error) return <Page title="Group" back={{ to: '/groups', label: 'Groups' }}><ErrorNote error={group.error} /></Page>

  return (
    <Page
      title={g ? `${kindEmoji(g.kind)} ${g.name}` : ' '}
      subtitle={g ? `${g.members.length} members · ${g.expense_count} expenses` : ' '}
      back={{ to: '/groups', label: 'Groups' }}
      actions={
        <Button size="sm" icon={<PlusIcon size={16} />} onClick={() => openAddExpense({ groupId: id })}>
          Expense
        </Button>
      }
    >
      {g ? (
        <div className="mb-6 grid grid-cols-2 gap-3">
          <Card className="p-4">
            <p className="text-[13px] font-medium text-label-2">Total spent</p>
            <Amount minor={g.total_spent} currency={g.currency} animated className="!text-label mt-0.5 block text-[24px] font-bold" />
          </Card>
          <Card className="p-4">
            <p className="text-[13px] font-medium text-label-2">{g.my_balance >= 0 ? 'You are owed' : 'You owe'}</p>
            <Amount minor={g.my_balance} currency={g.currency} animated className="mt-0.5 block text-[24px] font-bold" />
          </Card>
        </div>
      ) : (
        <Skeleton className="mb-6 h-[88px] rounded-[20px]" />
      )}

      <SegmentedControl
        label="Group sections"
        className="mb-6"
        value={tab}
        onChange={setTab}
        options={[
          { value: 'expenses', label: 'Expenses' },
          { value: 'balances', label: 'Balances' },
          { value: 'settle', label: 'Settle up' },
          { value: 'activity', label: 'Activity' },
        ]}
      />

      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
          {tab === 'expenses' && <ExpensesTab groupId={id} />}
          {tab === 'balances' && g && <BalancesTab groupId={id} />}
          {tab === 'settle' && <SettleTab groupId={id} />}
          {tab === 'activity' && <ActivityTab groupId={id} />}
        </motion.div>
      </AnimatePresence>
    </Page>
  )
}

function ExpensesTab({ groupId }: { groupId: number }) {
  const expenses = useExpenses({ group_id: groupId, limit: 200 })
  if (expenses.isLoading) return <Skeleton className="h-40 rounded-[20px]" />
  if (!expenses.data?.length) return <EmptyState icon="🧾" title="No expenses yet" body="Add the first one, or ask the assistant." />
  return <ExpenseList expenses={expenses.data} />
}

function BalancesTab({ groupId }: { groupId: number }) {
  const g = useGroup(groupId).data!
  const me = useAuth((s) => s.user)
  const add = useAddMember()
  const [email, setEmail] = useState('')
  function submit(e: FormEvent) {
    e.preventDefault()
    add.mutate({ groupId, email }, { onSuccess: () => setEmail('') })
  }
  return (
    <>
      <Section title="Members" footer="Positive = the group owes them; negative = they owe the group.">
        {g.members.map((m) => (
          <Row
            key={m.id}
            leading={<Avatar name={m.name} />}
            title={m.id === me?.id ? `${m.name} (you)` : m.name}
            subtitle={m.email}
            trailing={
              m.balance === 0 ? (
                <span className="text-[14px] text-label-2">settled up</span>
              ) : (
                <div className="leading-tight">
                  <div className={m.balance > 0 ? 'text-[12px] text-positive' : 'text-[12px] text-negative'}>{m.balance > 0 ? 'gets back' : 'owes'}</div>
                  <Amount minor={m.balance} currency={g.currency} className="text-[16px] font-semibold" />
                </div>
              )
            }
          />
        ))}
      </Section>
      <form onSubmit={submit} className="flex items-end gap-2">
        <TextField label="Add a member by email" type="email" placeholder="ananya@myshare.app" value={email} onChange={(e) => setEmail(e.target.value)} className="flex-1" required />
        <Button type="submit" variant="tinted" loading={add.isPending}>
          Add
        </Button>
      </form>
      <div className="mt-2">
        <ErrorNote error={add.error} />
      </div>
      <DeleteGroup groupId={groupId} />
    </>
  )
}

function DeleteGroup({ groupId }: { groupId: number }) {
  const g = useGroup(groupId).data
  const navigate = useNavigate()
  const del = useDeleteGroup(() => navigate('/groups', { replace: true }))
  const [confirming, setConfirming] = useState(false)
  if (!g) return null
  // The API refuses too; checking here just explains it before anyone tries.
  const settled = g.members.every((m) => m.balance === 0)
  return (
    <div className="mt-8 space-y-2">
      <ErrorNote error={del.error} />
      {confirming ? (
        <>
          <p className="px-1 text-[15px] text-label-2">
            Delete "{g.name}" and its {g.expense_count} expenses for all {g.members.length} members? This can't be undone.
          </p>
          <div className="flex gap-2">
            <Button variant="secondary" className="flex-1" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              className="flex-1"
              loading={del.isPending}
              onClick={() => del.mutate(groupId)}
            >
              Delete for everyone
            </Button>
          </div>
        </>
      ) : (
        <>
          <Button variant="destructive" className="w-full" icon={<TrashIcon size={18} />} disabled={!settled} onClick={() => setConfirming(true)}>
            Delete group
          </Button>
          {!settled && <p className="px-1 text-[13px] text-label-2">Everyone must be settled up before the group can be deleted.</p>}
        </>
      )}
    </div>
  )
}

function SettleTab({ groupId }: { groupId: number }) {
  const s = useSimplified(groupId)
  const me = useAuth((x) => x.user)
  const openSettle = useUI((x) => x.openSettle)
  if (s.isLoading || !s.data) return <Skeleton className="h-40 rounded-[20px]" />
  const d = s.data
  if (!d.transfers.length) return <EmptyState icon="🎉" title="Everyone is settled up" />
  const name = (u: { id: number; name: string }) => (u.id === me?.id ? 'You' : u.name.split(' ')[0])
  return (
    <Section
      title={`${d.transfers.length} payments settle everyone`}
      footer={`Simplified from ${d.original_transfer_count} separate debts by matching the biggest creditor with the biggest debtor.`}
    >
      {d.transfers.map((t, i) => (
        <motion.div
          key={i}
          className={listItemSeparator}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.05 }}
        >
          <Row
            leading={
              <div className="flex items-center -space-x-2">
                <Avatar name={t.from_user.name} size={34} />
                <Avatar name={t.to_user.name} size={34} />
              </div>
            }
            title={
              <span className="flex items-center gap-1.5">
                {name(t.from_user)} <ArrowRight size={16} className="text-label-3" /> {name(t.to_user)}
              </span>
            }
            subtitle={formatMoney(t.amount, d.currency)}
            trailing={
              <Button
                size="sm"
                variant="tinted"
                onClick={() => openSettle({ groupId, fromUserId: t.from_user.id, toUserId: t.to_user.id, amount: t.amount })}
              >
                Record
              </Button>
            }
          />
        </motion.div>
      ))}
    </Section>
  )
}

function ActivityTab({ groupId }: { groupId: number }) {
  const a = useActivity({ group_id: groupId, limit: 50 })
  return <Section>{a.data?.map((x) => <ActivityRow key={x.id} a={x} />) ?? <Skeleton className="m-4 h-10" />}</Section>
}

