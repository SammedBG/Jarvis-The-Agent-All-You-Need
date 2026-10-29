import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'

interface Daily { day: string; prompt_tokens: number; completion_tokens: number; total_tokens: number; calls: number }
interface ByRoute { route: string; prompt_tokens: number; completion_tokens: number; total_tokens: number; calls: number }

export function UsagePage() {
  const auth = useAuth()
  const [todayTokens, setTodayTokens] = useState(0)
  const [todayCalls, setTodayCalls] = useState(0)
  const [daily, setDaily] = useState<Daily[]>([])
  const [byRoute, setByRoute] = useState<ByRoute[]>([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!auth.loading && auth.user) load()
  }, [auth.loading, auth.user])

  async function load() {
    setErr(''); setMsg('')
    try {
      const d: any = await api.GET('/api/usage')
      setTodayTokens(d?.today_tokens || 0)
      setTodayCalls(d?.today_calls || 0)
      setDaily(d?.daily || [])
      setByRoute(d?.by_route || [])
      setMsg('Usage refreshed.')
    } catch (e: any) { setErr(e?.message || 'Failed to load usage') }
  }

  if (!auth.user) return <div className="app-shell-center muted">Loading usage…</div>

  return (
    <div className="page">
      <h2>Token & usage</h2>
      <p className="muted small">Groq token usage per day and per route, plus today's totals.</p>
      {err && <div className="error-text">{err}</div>}
      {msg && <div className="ok-text">{msg}</div>}

      <section className="card">
        <h3>Today</h3>
        <div className="stat-row">
          <div className="stat">
            <div className="stat-value">{todayTokens}</div>
            <div className="stat-label">tokens today</div>
          </div>
          <div className="stat">
            <div className="stat-value">{todayCalls}</div>
            <div className="stat-label">calls today</div>
          </div>
        </div>
      </section>

      <section className="card">
        <h3>Per day (last 30)</h3>
        {daily.length === 0 ? <p className="muted small">No daily data yet.</p> : (
          <table className="data-table">
            <thead>
              <tr><th>Day</th><th>Prompt tokens</th><th>Completion tokens</th><th>Total</th><th>Calls</th></tr>
            </thead>
            <tbody>
              {daily.map((d) => (
                <tr key={d.day}>
                  <td className="mono small">{d.day}</td>
                  <td className="mono small">{d.prompt_tokens}</td>
                  <td className="mono small">{d.completion_tokens}</td>
                  <td className="mono small">{d.total_tokens}</td>
                  <td className="mono small">{d.calls}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h3>Per route</h3>
        {byRoute.length === 0 ? <p className="muted small">No route data yet.</p> : (
          <table className="data-table">
            <thead>
              <tr><th>Route</th><th>Prompt tokens</th><th>Completion tokens</th><th>Total</th><th>Calls</th></tr>
            </thead>
            <tbody>
              {byRoute.map((r) => (
                <tr key={r.route}>
                  <td className="mono small">{r.route}</td>
                  <td className="mono small">{r.prompt_tokens}</td>
                  <td className="mono small">{r.completion_tokens}</td>
                  <td className="mono small">{r.total_tokens}</td>
                  <td className="mono small">{r.calls}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
