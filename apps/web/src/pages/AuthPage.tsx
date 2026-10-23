import { motion } from 'framer-motion'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { ThemeToggle } from '../components/layout/AppShell'
import { Button, ErrorNote, TextField } from '../components/ui/primitives'
import { spring } from '../lib/motion'
import { api } from '../lib/api'
import { useAuth } from '../lib/stores'

export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const setSession = useAuth((s) => s.setSession)
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent, demo = false) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const r =
        mode === 'signup' && !demo
          ? await api.signup(name, email, password)
          : await api.login(demo ? 'demo@myshare.app' : email, demo ? 'password123' : password)
      setSession(r.access_token, r.user)
      navigate('/')
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center p-4">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={spring} className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <img src="/favicon.svg" alt="" className="mx-auto mb-4 h-16 w-16 rounded-[18px] shadow-2" />
          <h1 className="text-[28px] font-bold tracking-tight">{mode === 'login' ? 'Welcome back' : 'Create your account'}</h1>
          <p className="mt-1 text-[15px] text-label-2">Split expenses with friends, without the awkward math.</p>
        </div>
        <form onSubmit={submit} className="space-y-3 rounded-[var(--radius-sheet)] bg-surface p-5 shadow-2">
          {mode === 'signup' && (
            <TextField label="Name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required />
          )}
          <TextField label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <TextField
            label="Password"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            minLength={mode === 'signup' ? 8 : undefined}
            hint={mode === 'signup' ? 'At least 8 characters' : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <ErrorNote error={error} />
          <Button type="submit" size="lg" className="w-full" loading={busy}>
            {mode === 'login' ? 'Log in' : 'Sign up'}
          </Button>
          {mode === 'login' && (
            <Button type="button" variant="tinted" size="lg" className="w-full" disabled={busy} onClick={(e) => submit(e, true)}>
              Use the demo account
            </Button>
          )}
        </form>
        <p className="mt-5 text-center text-[15px] text-label-2">
          {mode === 'login' ? (
            <>
              New here?{' '}
              <Link to="/signup" className="font-medium text-accent">
                Create an account
              </Link>
            </>
          ) : (
            <>
              Already have an account?{' '}
              <Link to="/login" className="font-medium text-accent">
                Log in
              </Link>
            </>
          )}
        </p>
      </motion.div>
    </div>
  )
}
