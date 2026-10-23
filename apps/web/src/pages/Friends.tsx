import { useState, type FormEvent } from 'react'
import { ExpenseList } from '../components/ExpenseList'
import { PlusIcon } from '../components/ui/icons'
import { Page } from '../components/ui/Page'
import { Amount, Avatar, BalanceLabel, Button, EmptyState, ErrorNote, Row, Section, Skeleton, TextField } from '../components/ui/primitives'
import { Sheet } from '../components/ui/Sheet'
import { useAddFriend, useExpenses, useFriend, useFriends } from '../lib/queries'
import { useAuth } from '../lib/stores'
import { useUI } from '../lib/ui'

export function Friends() {
  const friends = useFriends()
  const [selected, setSelected] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)

  return (
    <Page
      title="Friends"
      subtitle={friends.data ? `${friends.data.length} friends` : ' '}
      actions={
        <Button size="sm" variant="tinted" icon={<PlusIcon size={16} />} onClick={() => setAdding(true)}>
          Add friend
        </Button>
      }
    >
      <Section>
        {friends.isLoading && <Skeleton className="m-4 h-10" />}
        {friends.data?.map((f) => {
          const bal = f.balances[0]
          return (
            <Row
              key={f.id}
              onClick={() => setSelected(f.id)}
              leading={<Avatar name={f.name} />}
              title={f.name}
              subtitle={f.email}
              trailing={<BalanceLabel minor={bal?.amount ?? 0} currency={bal?.currency} />}
            />
          )
        })}
        {friends.data?.length === 0 && (
          <EmptyState icon="🫶" title="No friends yet" body="Add someone by the email they used to sign up." />
        )}
      </Section>
      <FriendSheet id={selected} onClose={() => setSelected(null)} />
      <AddFriendSheet open={adding} onClose={() => setAdding(false)} />
    </Page>
  )
}

function FriendSheet({ id, onClose }: { id: number | null; onClose: () => void }) {
  const friend = useFriend(id ?? 0)
  const expenses = useExpenses({ friend_id: id ?? undefined, limit: 30 })
  const me = useAuth((s) => s.user)
  const { openSettle, openAddExpense } = useUI()
  const f = friend.data
  const bal = f?.balances[0]
  return (
    <Sheet open={id !== null} onClose={onClose} title={f?.name ?? 'Friend'} widthClass="w-[min(620px,calc(100vw-32px))]">
      {f && (
        <div className="p-4">
          <div className="mb-5 flex items-center gap-4">
            <Avatar name={f.name} size={60} />
            <div>
              {bal && bal.amount !== 0 ? (
                <>
                  <p className="text-[15px] text-label-2">{bal.amount > 0 ? `${f.name.split(' ')[0]} owes you` : `You owe ${f.name.split(' ')[0]}`}</p>
                  <Amount minor={bal.amount} currency={bal.currency} animated className="text-[28px] font-bold" />
                </>
              ) : (
                <p className="text-[17px] text-label-2">You are settled up.</p>
              )}
            </div>
          </div>
          <div className="mb-6 flex gap-2">
            <Button className="flex-1" onClick={() => { onClose(); openAddExpense({ friendId: f.id }) }}>
              Add expense
            </Button>
            {bal && bal.amount !== 0 && (
              <Button
                variant="tinted"
                className="flex-1"
                onClick={() => {
                  onClose()
                  openSettle(bal.amount > 0 ? { fromUserId: f.id, toUserId: me?.id, amount: bal.amount } : { fromUserId: me?.id, toUserId: f.id, amount: -bal.amount })
                }}
              >
                Settle up
              </Button>
            )}
          </div>
          {f.breakdown.length > 0 && (
            <Section title="Balance by group">
              {f.breakdown.map((b) => (
                <Row
                  key={b.group_id ?? 'none'}
                  title={b.group_name}
                  trailing={<BalanceLabel minor={b.balances[0]?.amount ?? 0} currency={b.balances[0]?.currency} />}
                />
              ))}
            </Section>
          )}
          {expenses.data && <ExpenseList expenses={expenses.data} showGroup />}
        </div>
      )}
    </Sheet>
  )
}

function AddFriendSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [email, setEmail] = useState('')
  const add = useAddFriend()
  function submit(e: FormEvent) {
    e.preventDefault()
    add.mutate(email, {
      onSuccess: () => {
        setEmail('')
        onClose()
      },
    })
  }
  return (
    <Sheet open={open} onClose={onClose} title="Add a friend">
      <form onSubmit={submit} className="space-y-4 p-4">
        <TextField label="Their email" type="email" placeholder="priya@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <ErrorNote error={add.error} />
        <Button type="submit" size="lg" className="w-full" loading={add.isPending}>
          Add friend
        </Button>
      </form>
    </Sheet>
  )
}
