import { ActivityRow } from '../components/ExpenseList'
import { Page } from '../components/ui/Page'
import { EmptyState, Section, Skeleton } from '../components/ui/primitives'
import { useActivity } from '../lib/queries'
import type { Activity as A } from '../lib/types'

const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: 'long', day: 'numeric', month: 'long' })

function dayLabel(iso: string): string {
  const d = new Date(iso)
  const today = new Date()
  const yesterday = new Date(Date.now() - 86400_000)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return dayFmt.format(d)
}

export function Activity() {
  const activity = useActivity({ limit: 100 })
  const days = new Map<string, A[]>()
  for (const a of activity.data ?? []) {
    const k = dayLabel(a.created_at)
    days.set(k, [...(days.get(k) ?? []), a])
  }
  return (
    <Page title="Activity" subtitle="Everything that happened, newest first">
      {activity.isLoading && <Skeleton className="h-60 rounded-[20px]" />}
      {activity.data?.length === 0 && <EmptyState icon="🌱" title="No activity yet" />}
      {[...days].map(([day, items]) => (
        <Section key={day} title={day}>
          {items.map((a) => (
            <ActivityRow key={a.id} a={a} />
          ))}
        </Section>
      ))}
    </Page>
  )
}
