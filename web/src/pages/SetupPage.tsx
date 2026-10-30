import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

import { useEffect } from 'react'
// eslint-disable-next-line no-empty-pattern
export function SetupPage() {
  const auth = useAuth()
  const navigate = useNavigate()
  useEffect(() => {
    if (!auth.loading && auth.user) navigate('/', { replace: true })
    if (!auth.loading && !auth.needsSetup) navigate('/login', { replace: true })
  }, [auth.loading, auth.user, auth.needsSetup, navigate])
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (password.length < 12) {
      setError('Password must be at least 12 characters.')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/auth/setup', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (res.ok) {
        const login = await auth.login(username, password)
        if (login.ok) {
          await auth.refresh()
          navigate('/')
        } else {
          setError(login.error || 'Account created. Please sign in.')
          navigate('/login')
        }
      } else {
        const b = await res.json().catch(() => ({}))
        setError(b?.detail || 'Setup failed')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-shell-center">
      <div className="card auth-card">
        <h1 className="brand">JARVIS</h1>
        <p className="muted">Create owner password to get started.</p>
        <form onSubmit={submit} className="flex flex-col gap-3 mt-4">
          <label className="label">Username<input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required /></label>
          <label className="label">Password
            <div className="relative">
              <input className="input" type={show ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required minLength={12} />
              <button type="button" className="reveal" onClick={() => setShow((s) => !s)}>{show ? 'Hide' : 'Show'}</button>
            </div>
          </label>
          <label className="label">Confirm password<input className="input" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required /></label>
          {error && <div className="error-text">{error}</div>}
          <button className="btn-primary" type="submit" disabled={loading}>{loading ? 'Creating…' : 'Create password'}</button>
        </form>
      </div>
    </div>
  )
}
