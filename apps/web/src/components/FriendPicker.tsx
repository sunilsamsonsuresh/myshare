import clsx from 'clsx'
import { AnimatePresence, motion } from 'framer-motion'
import { useId, useState } from 'react'
import type { Friend } from '../lib/types'
import { CheckIcon } from './ui/icons'
import { Avatar } from './ui/primitives'

const SEARCH_AFTER = 6 // show a filter box once the list gets long

/**
 * A dropdown of your friends where you can tick several at once.
 *
 * The list opens inline (it pushes the form down) rather than floating, so it can't be
 * clipped by the sheet it lives in. Each row is a real checkbox, so keyboard and screen
 * reader support come for free: Tab to a friend, Space to tick.
 */
export function FriendPicker({
  friends,
  selected,
  onChange,
  label = 'Friends',
}: {
  friends: Friend[]
  selected: number[]
  onChange: (ids: number[]) => void
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const listId = useId()
  const chosen = friends.filter((f) => selected.includes(f.id))
  const shown = friends.filter((f) => `${f.name} ${f.email}`.toLowerCase().includes(filter.trim().toLowerCase()))
  const toggle = (id: number) => onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id])

  return (
    <div>
      <p className="mb-1 px-1 text-[13px] font-medium text-label-2">{label}</p>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === 'Escape' && open) {
            e.stopPropagation() // close the dropdown, not the whole sheet
            setOpen(false)
          }
        }}
        className="flex min-h-11 w-full items-center gap-2 rounded-[12px] bg-fill px-3.5 py-2 text-left text-[17px] focus:outline-none focus:ring-2 focus:ring-accent"
      >
        <span className={clsx('flex-1 truncate', !chosen.length && 'text-label-3')}>
          {chosen.length ? chosen.map((f) => f.name).join(', ') : friends.length ? 'Choose friends' : 'No friends yet'}
        </span>
        {chosen.length > 0 && (
          <span className="rounded-full bg-accent px-2 text-[13px] font-semibold text-white">{chosen.length}</span>
        )}
        <svg
          aria-hidden
          viewBox="0 0 24 24"
          width={14}
          height={14}
          fill="none"
          stroke="currentColor"
          strokeWidth={2.5}
          strokeLinecap="round"
          className={clsx('text-label-3 transition-transform', open && 'rotate-180')}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={listId}
            role="group"
            aria-label={label}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.stopPropagation()
                setOpen(false)
              }
            }}
          >
            <div className="mt-1.5 overflow-hidden rounded-[12px] bg-surface shadow-1">
              {friends.length > SEARCH_AFTER && (
                <input
                  type="search"
                  aria-label="Filter friends"
                  placeholder="Search"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="h-10 w-full border-b border-separator bg-transparent px-3.5 text-[15px] placeholder:text-label-3 focus:outline-none"
                />
              )}
              <ul className="max-h-60 overflow-y-auto">
                {shown.map((f) => {
                  const on = selected.includes(f.id)
                  return (
                    <li key={f.id}>
                      <label className="flex cursor-pointer items-center gap-3 px-3.5 py-2 hover:bg-fill has-[:focus-visible]:bg-fill">
                        <input type="checkbox" className="sr-only" checked={on} onChange={() => toggle(f.id)} />
                        <Avatar name={f.name} size={30} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[15px]">{f.name}</span>
                          <span className="block truncate text-[13px] text-label-2">{f.email}</span>
                        </span>
                        <span
                          aria-hidden
                          className={clsx(
                            'flex h-[22px] w-[22px] items-center justify-center rounded-full border-[1.5px] transition-colors',
                            on ? 'border-accent bg-accent text-white' : 'border-label-3',
                          )}
                        >
                          {on && <CheckIcon size={14} strokeWidth={3} />}
                        </span>
                      </label>
                    </li>
                  )
                })}
                {!shown.length && (
                  <li className="px-3.5 py-3 text-[15px] text-label-2">
                    {friends.length ? 'No friends match.' : 'Add friends on the Friends page, or invite by email below.'}
                  </li>
                )}
              </ul>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
