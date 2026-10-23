import { useAuth } from './stores'
import type {
  Activity,
  Expense,
  ExpenseInput,
  Friend,
  FriendDetail,
  Group,
  GroupDetail,
  GroupKind,
  Settlement,
  SettlementInput,
  SimplifiedDebts,
  Summary,
  User,
} from './types'

export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
export const HOST_URL = import.meta.env.VITE_HOST_URL ?? 'http://localhost:8002'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** FastAPI errors are {detail: string} or {detail: [{loc, msg}]}; turn either into one sentence. */
export function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail))
    return detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`).join('; ')
  return fallback
}

export async function request<T>(base: string, path: string, init: RequestInit = {}): Promise<T> {
  const token = useAuth.getState().token
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })
  if (res.status === 401 && token) useAuth.getState().logout()
  const body = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, errorMessage(body, res.statusText))
  return body as T
}

const get = <T>(path: string) => request<T>(API_URL, path)
const send = <T>(method: string, path: string, body?: unknown) =>
  request<T>(API_URL, path, { method, body: body === undefined ? undefined : JSON.stringify(body) })

const qs = (params: Record<string, string | number | null | undefined>) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  login: (email: string, password: string) =>
    send<{ access_token: string; user: User }>('POST', '/auth/login', { email, password }),
  signup: (name: string, email: string, password: string) =>
    send<{ access_token: string; user: User }>('POST', '/auth/signup', { name, email, password }),

  summary: () => get<Summary>('/users/me/summary'),
  friends: () => get<Friend[]>('/friends'),
  friend: (id: number) => get<FriendDetail>(`/friends/${id}`),
  addFriend: (email: string) => send<Friend>('POST', '/friends', { email }),

  groups: () => get<Group[]>('/groups'),
  group: (id: number) => get<GroupDetail>(`/groups/${id}`),
  createGroup: (body: { name: string; kind: GroupKind; currency: string; member_emails: string[] }) =>
    send<GroupDetail>('POST', '/groups', body),
  deleteGroup: (id: number) => send<GroupDetail>('DELETE', `/groups/${id}`),
  addMember: (groupId: number, email: string) => send<GroupDetail>('POST', `/groups/${groupId}/members`, { email }),
  simplified: (groupId: number) => get<SimplifiedDebts>(`/groups/${groupId}/simplified-debts`),

  expenses: (params: { group_id?: number; friend_id?: number; q?: string; limit?: number } = {}) =>
    get<Expense[]>(`/expenses${qs(params)}`),
  addExpense: (body: ExpenseInput) => send<Expense>('POST', '/expenses', body),
  deleteExpense: (id: number) => send<Expense>('DELETE', `/expenses/${id}`),

  settle: (body: SettlementInput) => send<Settlement>('POST', '/settlements', body),
  activity: (params: { group_id?: number; limit?: number } = {}) => get<Activity[]>(`/activity${qs(params)}`),
}
