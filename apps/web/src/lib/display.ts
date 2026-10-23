// Small display helpers shared across pages.

const CATEGORY_EMOJI: Record<string, string> = {
  food: '🍽️',
  groceries: '🛒',
  transport: '🚕',
  lodging: '🏨',
  travel: '✈️',
  rent: '🏠',
  utilities: '💡',
  entertainment: '🎟️',
  shopping: '🛍️',
  health: '💊',
  general: '🧾',
  other: '🧾',
}
export const categoryEmoji = (c: string) => CATEGORY_EMOJI[c] ?? '🧾'

const KIND_EMOJI: Record<string, string> = { trip: '🏝️', home: '🏠', couple: '💞', dinner: '🍝', other: '👥' }
export const kindEmoji = (k: string) => KIND_EMOJI[k] ?? '👥'

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
export function timeAgo(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return relative.format(-Math.round(s / 60), 'minute')
  if (s < 86400) return relative.format(-Math.round(s / 3600), 'hour')
  if (s < 86400 * 7) return relative.format(-Math.round(s / 86400), 'day')
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

/** For <li> wrappers around Rows: an inset hairline between items (not after the last). */
export const listItemSeparator =
  'relative after:absolute after:bottom-0 after:left-16 after:right-0 after:h-px after:origin-bottom after:scale-y-50 after:bg-separator last:after:hidden'
