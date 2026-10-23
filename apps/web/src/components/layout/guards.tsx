import type { ReactNode } from 'react'
import { Navigate } from 'react-router'
import { useAuth } from '../../lib/stores'

export function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuth((s) => s.token)
  return token ? children : <Navigate to="/login" replace />
}

export function GuestOnly({ children }: { children: ReactNode }) {
  const token = useAuth((s) => s.token)
  return token ? <Navigate to="/" replace /> : children
}
