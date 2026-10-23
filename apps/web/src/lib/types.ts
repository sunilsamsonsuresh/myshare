// Shapes returned by the MyShare REST API (apps/api/myshare_api/schemas.py).
// All money fields are integer minor units (paise / cents).

export interface User {
  id: number
  email: string
  name: string
}

export interface Money {
  currency: string
  amount: number // signed: >0 owed to you, <0 you owe
}

export interface OverallBalance {
  currency: string
  owed_to_you: number
  you_owe: number
  net: number
}

export interface Summary {
  user: User
  default_currency: string
  balances: OverallBalance[]
  friend_count: number
  group_count: number
}

export interface Friend extends User {
  balances: Money[]
}

export interface FriendDetail extends Friend {
  breakdown: { group_id: number | null; group_name: string; balances: Money[] }[]
}

export type GroupKind = 'trip' | 'home' | 'couple' | 'dinner' | 'other'

export interface Group {
  id: number
  name: string
  kind: GroupKind
  currency: string
  created_at: string
  member_count: number
  my_balance: number
}

export interface GroupMember extends User {
  balance: number
}

export interface GroupDetail extends Group {
  members: GroupMember[]
  total_spent: number
  expense_count: number
}

export type SplitType = 'equal' | 'exact' | 'percent' | 'shares'

export interface Expense {
  id: number
  group_id: number | null
  group_name: string | null
  description: string
  amount: number
  currency: string
  date: string
  category: string
  payer: User
  split_type: SplitType
  splits: { user: User; owed_amount: number; share_value: string | null }[]
  created_by: number
  created_at: string
  updated_at: string
  my_net: number
}

export interface ExpenseInput {
  group_id?: number | null
  friend_id?: number | null
  description: string
  amount: number
  currency?: string
  date?: string
  category: string
  payer_id: number
  split: { type: SplitType; participants: { user_id: number; value?: string | number | null }[] }
}

export interface Settlement {
  id: number
  group_id: number | null
  from_user: User
  to_user: User
  amount: number
  currency: string
  date: string
  note: string | null
  created_at: string
}

export interface SettlementInput {
  from_user_id: number
  to_user_id: number
  amount: number
  group_id?: number | null
  note?: string
}

export interface SimplifiedDebts {
  group_id: number
  group_name: string
  currency: string
  transfers: { from_user: User; to_user: User; amount: number }[]
  original_transfer_count: number
}

export interface Activity {
  id: number
  verb: string
  summary: string
  actor: User
  group_id: number | null
  expense_id: number | null
  settlement_id: number | null
  data: Record<string, unknown>
  created_at: string
}

export const CATEGORIES = [
  'general',
  'food',
  'groceries',
  'transport',
  'lodging',
  'travel',
  'rent',
  'utilities',
  'entertainment',
  'shopping',
  'health',
  'other',
] as const
