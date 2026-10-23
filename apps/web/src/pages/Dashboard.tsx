import { motion } from 'framer-motion'
import { useNavigate } from 'react-router'
import { ActivityRow } from '../components/ExpenseList'
import { PlusIcon } from '../components/ui/icons'
import { kindEmoji } from '../lib/display'
import { Page } from '../components/ui/Page'
import { Amount, Button, Card, EmojiTile, Row, Section, Skeleton } from '../components/ui/primitives'
import { spring } from '../lib/motion'
import { useActivity, useGroups, useSummary } from '../lib/queries'
import { useAuth } from '../lib/stores'
import { useUI } from '../lib/ui'

function BalanceCard({ label, minor, currency, tone, delay }: { label: string; minor: number; currency: string; tone: 'positive' | 'negative'; delay: number }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay }}>
      <Card className="relative overflow-hidden p-5">
        <div
          aria-hidden
          className="absolute -right-8 -top-10 h-32 w-32 rounded-full opacity-60 blur-2xl"
          style={{ background: tone === 'positive' ? 'var(--positive-soft)' : 'var(--negative-soft)' }}
        />
        <p className="relative text-[15px] font-medium text-label-2">{label}</p>
        <Amount
          minor={tone === 'positive' ? minor : -minor}
          currency={currency}
          animated
          className="relative mt-1 block text-[32px] font-bold tracking-tight"
        />
      </Card>
    </motion.div>
  )
}

export function Dashboard() {
  const user = useAuth((s) => s.user)
  const summary = useSummary()
  const groups = useGroups()
  const activity = useActivity({ limit: 5 })
  const openAddExpense = useUI((s) => s.openAddExpense)
  const navigate = useNavigate()

  const b = summary.data?.balances[0]
  const currency = b?.currency ?? summary.data?.default_currency ?? 'INR'
  const net = b?.net ?? 0
  const greeting = new Date().getHours() < 12 ? 'Good morning' : new Date().getHours() < 18 ? 'Good afternoon' : 'Good evening'

  return (
    <Page
      title={`${greeting}, ${user?.name.split(' ')[0] ?? ''}`}
      subtitle={
        summary.data ? (
          net === 0 ? (
            'You are all settled up.'
          ) : (
            <>
              Overall, {net > 0 ? 'you are owed ' : 'you owe '}
              <Amount minor={net} currency={currency} className="font-semibold" />
            </>
          )
        ) : (
          ' '
        )
      }
      actions={
        <Button size="sm" icon={<PlusIcon size={16} />} onClick={() => openAddExpense()} className="md:hidden">
          Add
        </Button>
      }
    >
      <div className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {summary.isLoading ? (
          <>
            <Skeleton className="h-[108px] rounded-[20px]" />
            <Skeleton className="h-[108px] rounded-[20px]" />
          </>
        ) : (
          <>
            <BalanceCard label="You are owed" minor={b?.owed_to_you ?? 0} currency={currency} tone="positive" delay={0} />
            <BalanceCard label="You owe" minor={b?.you_owe ?? 0} currency={currency} tone="negative" delay={0.06} />
          </>
        )}
      </div>

      <Section title="Groups">
        {groups.isLoading && <Skeleton className="m-4 h-10" />}
        {groups.data?.map((g) => (
          <Row
            key={g.id}
            onClick={() => navigate(`/groups/${g.id}`)}
            leading={<EmojiTile emoji={kindEmoji(g.kind)} />}
            title={g.name}
            subtitle={`${g.member_count} members`}
            trailing={
              g.my_balance === 0 ? (
                <span className="text-[14px] text-label-2">settled up</span>
              ) : (
                <div className="leading-tight">
                  <div className={g.my_balance > 0 ? 'text-[12px] text-positive' : 'text-[12px] text-negative'}>
                    {g.my_balance > 0 ? 'you are owed' : 'you owe'}
                  </div>
                  <Amount minor={g.my_balance} currency={g.currency} className="text-[16px] font-semibold" />
                </div>
              )
            }
          />
        ))}
      </Section>

      <Section
        title="Recent activity"
        action={
          <button onClick={() => navigate('/activity')} className="text-[15px] text-accent">
            See all
          </button>
        }
      >
        {activity.data?.map((a) => <ActivityRow key={a.id} a={a} />)}
        {activity.data?.length === 0 && <p className="p-4 text-label-2">Nothing yet.</p>}
      </Section>
    </Page>
  )
}
