import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function LoginPage() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [lockout, setLockout] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!auth.loading) {
      if (auth.user) navigate('/', { replace: true })
      else if (auth.needsSetup) navigate('/setup', { replace: true })
    }
  }, [auth.loading, auth.user, auth.needsSetup, navigate])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    setLockout('')
    const res = await auth.login(username, password)
    if (res.ok) {
      navigate('/', { replace: true })
    } else {
      if (res.lockoutUntil) {
        setLockout(`Too many attempts. Try again at ${res.lockoutUntil}.`)
      }
      setError(res.error || 'Invalid credentials')
    }
    setLoading(false)
  }

  return (
    <div className="app-shell-center">
      <div className="card auth-card">
        <h1 className="brand">JARVIS</h1>
        <p className="muted">Sign in to continue.</p>
        <form onSubmit={submit} className="flex flex-col gap-3 mt-4">
          <label className="label">Username<input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required /></label>
          <label className="label">Password
            <div className="relative">
              <input className="input" type={show ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
              <button type="button" className="reveal" onClick={() => setShow((s) => !s)}>{show ? 'Hide' : 'Show'}</button>
            </div>
          </label>
          {lockout && <div className="error-text">{lockout}</div>}
          {error && <div className="error-text">{error}</div>}
          <button className="btn-primary" type="submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</button>
        </form>
        {auth.needsSetup && <p className="muted mt-4 small">First time? Set up your password.</p>}
      </div>
    </div>
  )
}
