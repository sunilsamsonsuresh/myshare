import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from './types'

// ---------------------------------------------------------------- auth
interface AuthState {
  token: string | null
  user: User | null
  setSession: (token: string, user: User) => void
  logout: () => void
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setSession: (token, user) => set({ token, user }),
      logout: () => set({ token: null, user: null }),
    }),
    { name: 'myshare-auth' },
  ),
)

// ---------------------------------------------------------------- theme
export type ThemePref = 'system' | 'light' | 'dark'

interface ThemeState {
  theme: ThemePref
  setTheme: (t: ThemePref) => void
}

const media = () => window.matchMedia('(prefers-color-scheme: dark)')

export function applyTheme(theme: ThemePref) {
  const dark = theme === 'dark' || (theme === 'system' && media().matches)
  document.documentElement.classList.toggle('dark', dark)
}

export const useTheme = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'system',
      setTheme: (theme) => {
        applyTheme(theme)
        set({ theme })
      },
    }),
    { name: 'myshare-theme' },
  ),
)

// Follow OS changes while the preference is "system".
media().addEventListener?.('change', () => applyTheme(useTheme.getState().theme))
