import clsx from 'clsx'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import type { ReactNode } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'
import { ChatLauncher } from '../../chat/ChatLauncher'
import { useChat } from '../../chat/store'
import { useAuth, useTheme, type ThemePref } from '../../lib/stores'
import { AddExpenseSheet } from '../AddExpenseSheet'
import { SettleSheet } from '../SettleSheet'
import { ActivityIcon, GroupsIcon, HomeIcon, LogoutIcon, MonitorIcon, MoonIcon, PeopleIcon, PlusIcon, SunIcon } from '../ui/icons'
import { Avatar, Button } from '../ui/primitives'
import { useUI } from '../../lib/ui'

const NAV = [
  { to: '/', label: 'Home', icon: HomeIcon, end: true },
  { to: '/friends', label: 'Friends', icon: PeopleIcon },
  { to: '/groups', label: 'Groups', icon: GroupsIcon },
  { to: '/activity', label: 'Activity', icon: ActivityIcon },
]

const THEMES: { value: ThemePref; label: string; icon: ReactNode }[] = [
  { value: 'system', label: 'System theme', icon: <MonitorIcon size={16} /> },
  { value: 'light', label: 'Light theme', icon: <SunIcon size={16} /> },
  { value: 'dark', label: 'Dark theme', icon: <MoonIcon size={16} /> },
]

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  return (
    <div role="radiogroup" aria-label="Appearance" className="flex rounded-full bg-fill p-0.5">
      {THEMES.map((t) => (
        <button
          key={t.value}
          role="radio"
          aria-checked={theme === t.value}
          aria-label={t.label}
          title={t.label}
          onClick={() => setTheme(t.value)}
          className={clsx(
            'flex h-7 w-8 items-center justify-center rounded-full transition',
            theme === t.value ? 'bg-raised text-label shadow-1' : 'text-label-2 hover:text-label',
          )}
        >
          {t.icon}
        </button>
      ))}
    </div>
  )
}

function Sidebar() {
  const { user, logout } = useAuth()
  const openAddExpense = useUI((s) => s.openAddExpense)
  return (
    <aside className="material fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-[var(--material-border)] px-3 py-5 md:flex">
      <div className="mb-6 flex items-center gap-2.5 px-3">
        <img src="/favicon.svg" alt="" className="h-8 w-8 rounded-[9px] shadow-1" />
        <span className="text-[20px] font-bold tracking-tight">MyShare</span>
      </div>
      <nav aria-label="Main" className="flex flex-col gap-0.5">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 rounded-[10px] px-3 py-2 text-[15px] font-medium transition-colors',
                isActive ? 'bg-accent text-white' : 'text-label hover:bg-fill',
              )
            }
          >
            <Icon size={20} />
            {label}
          </NavLink>
        ))}
      </nav>
      <Button className="mx-1 mt-5" icon={<PlusIcon size={18} />} onClick={() => openAddExpense()}>
        Add expense
      </Button>
      <div className="mt-auto space-y-3 px-1">
        <ThemeToggle />
        {user && (
          <div className="flex items-center gap-2.5 rounded-[12px] px-2 py-1.5">
            <Avatar name={user.name} size={32} />
            <div className="min-w-0 flex-1 leading-tight">
              <div className="truncate text-[14px] font-semibold">{user.name}</div>
              <div className="truncate text-[12px] text-label-2">{user.email}</div>
            </div>
            <button
              onClick={logout}
              aria-label="Log out"
              title="Log out"
              className="rounded-full p-1.5 text-label-2 hover:bg-fill hover:text-label"
            >
              <LogoutIcon size={18} />
            </button>
          </div>
        )}
      </div>
    </aside>
  )
}

function TabBar() {
  return (
    <nav
      aria-label="Main"
      className="material hairline-t fixed inset-x-0 bottom-0 z-40 flex pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            clsx(
              'flex flex-1 flex-col items-center gap-0.5 pb-1.5 pt-2 text-[10px] font-medium',
              isActive ? 'text-accent' : 'text-label-2',
            )
          }
        >
          <Icon size={24} />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

export function AppShell() {
  const location = useLocation()
  const reduce = useReducedMotion()
  const chatOpen = useChat((s) => s.open)
  return (
    <div className="min-h-dvh">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[60] focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <Sidebar />
      {/* On wide screens, make room for the docked chat panel so the live-updating page stays visible. */}
      <div id="content" className={clsx('transition-[padding] duration-300 md:pl-64', chatOpen && 'xl:pr-[432px]')}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={location.pathname}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -4 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </div>
      <TabBar />
      <AddExpenseSheet />
      <SettleSheet />
      <ChatLauncher />
    </div>
  )
}
