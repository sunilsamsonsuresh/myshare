import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { FriendPicker } from '../components/FriendPicker'
import { PlusIcon } from '../components/ui/icons'
import { kindEmoji } from '../lib/display'
import { Page } from '../components/ui/Page'
import { Amount, Button, EmojiTile, EmptyState, ErrorNote, Row, Section, SegmentedControl, Skeleton, TextField } from '../components/ui/primitives'
import { Sheet } from '../components/ui/Sheet'
import { useCreateGroup, useFriends, useGroups } from '../lib/queries'
import type { GroupKind } from '../lib/types'

export function Groups() {
  const groups = useGroups()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)
  return (
    <Page
      title="Groups"
      subtitle={groups.data ? `${groups.data.length} groups` : ' '}
      actions={
        <Button size="sm" variant="tinted" icon={<PlusIcon size={16} />} onClick={() => setCreating(true)}>
          New group
        </Button>
      }
    >
      <Section>
        {groups.isLoading && <Skeleton className="m-4 h-10" />}
        {groups.data?.map((g) => (
          <Row
            key={g.id}
            onClick={() => navigate(`/groups/${g.id}`)}
            leading={<EmojiTile emoji={kindEmoji(g.kind)} />}
            title={g.name}
            subtitle={`${g.member_count} members · ${g.currency}`}
            trailing={
              g.my_balance === 0 ? (
                <span className="text-[14px] text-label-2">settled up</span>
              ) : (
                <Amount minor={g.my_balance} currency={g.currency} signed className="text-[16px] font-semibold" />
              )
            }
          />
        ))}
        {groups.data?.length === 0 && <EmptyState icon="👥" title="No groups yet" body="Create one for a trip, a flat, or a dinner." />}
      </Section>
      <CreateGroupSheet open={creating} onClose={() => setCreating(false)} />
    </Page>
  )
}

const KINDS: { value: GroupKind; label: string }[] = [
  { value: 'trip', label: '🏝️ Trip' },
  { value: 'home', label: '🏠 Home' },
  { value: 'dinner', label: '🍝 Dinner' },
  { value: 'other', label: '👥 Other' },
]

function CreateGroupSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState('')
  const [kind, setKind] = useState<GroupKind>('trip')
  const [friendIds, setFriendIds] = useState<number[]>([])
  const [emails, setEmails] = useState('')
  const friends = useFriends()
  const create = useCreateGroup()
  const navigate = useNavigate()
  function submit(e: FormEvent) {
    e.preventDefault()
    // The API takes emails, so picked friends and typed emails end up in the same list.
    const picked = (friends.data ?? []).filter((f) => friendIds.includes(f.id)).map((f) => f.email)
    const member_emails = [...picked, ...emails.split(/[\s,;]+/).filter(Boolean)]
    create.mutate(
      { name, kind, currency: 'INR', member_emails },
      {
        onSuccess: (g) => {
          onClose()
          setName('')
          setFriendIds([])
          setEmails('')
          navigate(`/groups/${g.id}`)
        },
      },
    )
  }
  return (
    <Sheet open={open} onClose={onClose} title="New group">
      <form onSubmit={submit} className="space-y-4 p-4">
        <TextField label="Name" placeholder="Goa Trip" value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} />
        <div>
          <p className="mb-1.5 px-1 text-[13px] font-medium text-label-2">Type</p>
          <SegmentedControl label="Group type" options={KINDS} value={kind} onChange={setKind} />
        </div>
        <FriendPicker label="Members" friends={friends.data ?? []} selected={friendIds} onChange={setFriendIds} />
        <TextField
          label="Or invite by email"
          placeholder="someone@example.com"
          hint="For people who aren't your friends yet. They need a MyShare account. You're added automatically."
          value={emails}
          onChange={(e) => setEmails(e.target.value)}
        />
        <ErrorNote error={create.error} />
        <Button type="submit" size="lg" className="w-full" loading={create.isPending}>
          Create group
        </Button>
      </form>
    </Sheet>
  )
}
