import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import type { ExpenseInput, GroupKind, SettlementInput } from './types'

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: true } },
})

// Query keys. Every key starts with the resource name, so invalidating ['groups']
// refreshes the list AND every group's details.
export const keys = {
  summary: ['summary'] as const,
  friends: ['friends'] as const,
  friend: (id: number) => ['friends', id] as const,
  groups: ['groups'] as const,
  group: (id: number) => ['groups', id] as const,
  simplified: (id: number) => ['groups', id, 'simplified'] as const,
  expenses: (params: object = {}) => ['expenses', params] as const,
  activity: (params: object = {}) => ['activity', params] as const,
}

/** Everything derived from expenses: after any write, all of it may have changed. */
const MONEY_KEYS = ['summary', 'friends', 'groups', 'expenses', 'activity']

export function invalidateMoney(qc: QueryClient = queryClient) {
  for (const k of MONEY_KEYS) qc.invalidateQueries({ queryKey: [k] })
}

export const useSummary = () => useQuery({ queryKey: keys.summary, queryFn: api.summary })
export const useFriends = () => useQuery({ queryKey: keys.friends, queryFn: api.friends })
export const useFriend = (id: number) =>
  useQuery({ queryKey: keys.friend(id), queryFn: () => api.friend(id), enabled: id > 0 })
export const useGroups = () => useQuery({ queryKey: keys.groups, queryFn: api.groups })
export const useGroup = (id: number) =>
  useQuery({ queryKey: keys.group(id), queryFn: () => api.group(id), enabled: id > 0 })
export const useSimplified = (id: number) =>
  useQuery({ queryKey: keys.simplified(id), queryFn: () => api.simplified(id), enabled: id > 0 })
export const useExpenses = (params: { group_id?: number; friend_id?: number; limit?: number } = {}) =>
  useQuery({ queryKey: keys.expenses(params), queryFn: () => api.expenses(params) })
export const useActivity = (params: { group_id?: number; limit?: number } = {}) =>
  useQuery({ queryKey: keys.activity(params), queryFn: () => api.activity(params) })

function useWrite<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => invalidateMoney(qc) })
}

export const useAddExpense = () => useWrite((body: ExpenseInput) => api.addExpense(body))
export const useDeleteExpense = () => useWrite((id: number) => api.deleteExpense(id))
export const useSettle = () => useWrite((body: SettlementInput) => api.settle(body))
export const useAddFriend = () => useWrite((email: string) => api.addFriend(email))
export const useAddMember = () => useWrite((a: { groupId: number; email: string }) => api.addMember(a.groupId, a.email))
export const useCreateGroup = () =>
  useWrite((body: { name: string; kind: GroupKind; currency: string; member_emails: string[] }) => api.createGroup(body))
/**
 * Deleting the group the user is looking at. Refresh everything EXCEPT that group's own
 * queries: the open page is still subscribed to them, and refetching would just 404.
 * Once the page is gone they're unused, and TanStack Query garbage-collects them.
 */
export const useDeleteGroup = (onDeleted: () => void) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.deleteGroup(id),
    onSuccess: (_, id) => {
      onDeleted()
      qc.invalidateQueries({
        predicate: ({ queryKey: [kind, groupId] }) => MONEY_KEYS.includes(kind as string) && !(kind === 'groups' && groupId === id),
      })
    },
  })
}
