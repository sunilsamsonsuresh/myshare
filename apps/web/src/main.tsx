import { QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'framer-motion'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router'
import { GuestOnly, RequireAuth } from './components/layout/guards'
import { AppShell } from './components/layout/AppShell'
import './index.css'
import { queryClient } from './lib/queries'
import { applyTheme, useTheme } from './lib/stores'
import { Activity } from './pages/Activity'
import { AuthPage } from './pages/AuthPage'
import { Dashboard } from './pages/Dashboard'
import { Friends } from './pages/Friends'
import { GroupDetail } from './pages/GroupDetail'
import { Groups } from './pages/Groups'

applyTheme(useTheme.getState().theme)

const router = createBrowserRouter([
  { path: '/login', element: <GuestOnly><AuthPage mode="login" /></GuestOnly> },
  { path: '/signup', element: <GuestOnly><AuthPage mode="signup" /></GuestOnly> },
  {
    path: '/',
    element: <RequireAuth><AppShell /></RequireAuth>,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'friends', element: <Friends /> },
      { path: 'groups', element: <Groups /> },
      { path: 'groups/:id', element: <GroupDetail /> },
      { path: 'activity', element: <Activity /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {/* reducedMotion="user": every framer-motion animation honours prefers-reduced-motion. */}
      <MotionConfig reducedMotion="user">
        <RouterProvider router={router} />
      </MotionConfig>
    </QueryClientProvider>
  </StrictMode>,
)
