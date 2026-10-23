import { create } from 'zustand'

// Global modal state, so "Add expense" / "Settle up" can be opened from anywhere.
// `nonce` changes on every open; sheets use it as a React key so their forms start fresh.
interface UIState {
  addExpense: { open: boolean; nonce?: number; groupId?: number; friendId?: number }
  settle: { open: boolean; nonce?: number; groupId?: number; fromUserId?: number; toUserId?: number; amount?: number }
  openAddExpense: (ctx?: { groupId?: number; friendId?: number }) => void
  openSettle: (ctx?: { groupId?: number; fromUserId?: number; toUserId?: number; amount?: number }) => void
  closeAll: () => void
}

export const useUI = create<UIState>()((set) => ({
  addExpense: { open: false },
  settle: { open: false },
  openAddExpense: (ctx = {}) => set({ addExpense: { open: true, nonce: Date.now(), ...ctx } }),
  openSettle: (ctx = {}) => set({ settle: { open: true, nonce: Date.now(), ...ctx } }),
  closeAll: () =>
    set((s) => ({ addExpense: { ...s.addExpense, open: false }, settle: { ...s.settle, open: false } })),
}))
