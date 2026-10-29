import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import type { ReactNode } from 'react'
import { fetchMe, clearCsrf, setUnauthorizedHandler, api } from '../lib/api'

export interface AuthUser {
  id: number
  username: string
  csrf_token: string
}

interface AuthContextValue {
  user: AuthUser | null
  loading: boolean
  needsSetup: boolean
  login: (username: string, password: string) => Promise<{ ok: boolean; error?: string; lockoutUntil?: string }>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [needsSetup, setNeedsSetup] = useState(false)

  const refresh = useCallback(async () => {
    const u = await fetchMe()
    if (u) {
      setUser(u)
    } else {
      setUser(null)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        // Probe first-run
        const me = await fetchMe()
        if (me && !cancelled) {
          setUser(me)
          setNeedsSetup(false)
          setLoading(false)
          return
        }
        // If no session, probe setup
        const base = (typeof window !== 'undefined' && window.location?.origin) ? window.location.origin : 'http://localhost:5173'
        let probeRes: any = null
        try {
          probeRes = await fetch(`${base}/api/auth/setup`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: '', password: '' }),
          })
        } catch {
          probeRes = null
        }
        if (cancelled) return
        let isConfigured = false
        try {
          const json = await probeRes.json()
          isConfigured = false
          void json
        } catch {
          isConfigured = false
        }
        if (probeRes !== null && probeRes.status === 403) {
          try {
            const j = await probeRes.clone().json()
            if (j?.detail === 'auth already configured') isConfigured = true
          } catch { /* */ }
        }
        setNeedsSetup(!isConfigured)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null)
      clearCsrf()
    })
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        if (res.status === 403 && /lockout|too many/i.test(body?.detail || '')) {
          // parse retry time from body? generic
          return { ok: false, error: body?.detail || 'Locked out', lockoutUntil: undefined }
        }
        return { ok: false, error: body?.detail || 'Invalid credentials' }
      }
      await refresh()
      return { ok: true }
    } catch (e) {
      return { ok: false, error: 'Network error - please retry' }
    }
  }, [refresh])

  const logout = useCallback(async () => {
    const u = user
    if (u) {
      try { await api.POST('/api/auth/logout', {}) } catch { /* ignore */ }
    }
    setUser(null)
    clearCsrf()
  }, [user])

  return (
    <AuthContext.Provider value={{ user, loading, needsSetup, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}