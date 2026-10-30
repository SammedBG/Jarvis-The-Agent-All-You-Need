import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'

interface Activity { ts: string; tool: string; status: string; text: string }

export function ActivityPage() {
  const auth = useAuth()
  const [items, setItems] = useState<Activity[]>([])
  const [limit, setLimit] = useState(50)
  const [toolFilter, setToolFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [sinceFilter, setSinceFilter] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!auth.loading && auth.user) load()
  }, [auth.loading, auth.user, limit, toolFilter, statusFilter, sinceFilter])

  async function load() {
    setErr(''); setMsg('')
    try {
      const params = new URLSearchParams({ limit: String(limit) })
      if (toolFilter) params.set('tool', toolFilter)
      if (statusFilter) params.set('status', statusFilter)
      if (sinceFilter) params.set('since', sinceFilter)
      const d: any = await api.GET(`/api/activity?${params.toString()}`)
      setItems(d?.activities || [])
      setMsg(`Loaded ${(d?.activities || []).length} activity entries.`)
    } catch (e: any) { setErr(e?.message || 'Failed to load activity') }
  }

  if (!auth.user) return <div className="app-shell-center muted">Loading activity…</div>

  return (
    <div className="page">
      <h2>Activity log</h2>
      <p className="muted small">Redacted timeline of tool calls and approval decisions. Sensitive values are masked.</p>
      {err && <div className="error-text">{err}</div>}
      {msg && <div className="ok-text">{msg}</div>}

      <div className="filter-row">
        <input className="input" placeholder="Filter by tool" value={toolFilter} onChange={(e) => setToolFilter(e.target.value)} />
        <input className="input" placeholder="Filter by status (ok/error/declined/rate_limited)" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} />
        <input className="input" type="date" placeholder="Since" value={sinceFilter} onChange={(e) => setSinceFilter(e.target.value)} />
        <label className="label">Limit</label>
        <input className="input" type="number" min="1" max="1000" value={limit} onChange={(e) => setLimit(parseInt(e.target.value || '50', 10))} />
        <button className="btn-primary" onClick={load}>Refresh</button>
      </div>

      {items.length === 0 ? (
        <p className="muted small">No activity entries yet.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr><th>Time</th><th>Tool</th><th>Status</th><th>Detail (redacted)</th></tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.ts + a.tool}>
                <td className="mono small">{a.ts}</td>
                <td className="mono small">{a.tool}</td>
                <td><span className={`chip ${a.status}`}>{a.status}</span></td>
                <td className="mono small" title={a.text}>{a.text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
