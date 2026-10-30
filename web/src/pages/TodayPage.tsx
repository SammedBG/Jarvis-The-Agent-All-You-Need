import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'

export function TodayPage() {
  const auth = useAuth()
  const [briefing, setBriefing] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [quick, setQuick] = useState('')

  useEffect(() => {
    if (!auth.loading && !auth.user) return // route guard handled at App
    if (!auth.loading && auth.user) load()
  }, [auth.loading, auth.user])

  async function load() {
    try {
      setBriefing(await api.GET('/api/briefing'))
      await api.GET('/api/tasks?view=all')
    } catch (e: any) {}
  }

  async function addQuick() {
    if (!quick.trim()) return
    setBusy(true)
    try { await api.POST('/api/tasks', { title: quick.trim() }); setQuick(''); await load() }
    catch (e: any) {}
    setBusy(false)
  }

  async function refresh() {
    setBusy(true)
    try { setBriefing(await api.GET('/api/briefing')) } catch {}
    setBusy(false)
  }

  return (
    <div className="page">
      <h2>Today</h2>
      <section className="card">
        <div className="section-header">
          <h3>Daily briefing</h3>
          <button className="btn-link" onClick={refresh} disabled={busy}>{busy ? 'Refreshing…' : 'Refresh'}</button>
        </div>
        {briefing?.date && <p className="muted small">{briefing.date}</p>}
        <p className="muted">{briefing?.text || 'No briefing yet. Press Refresh to generate.'}</p>
        {briefing?.sections?.map((sec: any) => (
          <div key={sec.title} className="assist-block">
            <div className="assist-title">{sec.title}</div>
            {sec.items?.length > 0 ? (
              <ul className="assist-ul">{sec.items.map((it: any, i: number) => <li key={i}>{it}</li>)}</ul>
            ) : <div className="muted small">none</div>}
          </div>
        ))}
      </section>
      <section className="card">
        <h3>Quick add</h3>
        <div className="flex-row">
          <input className="input" value={quick} onChange={(e) => setQuick(e.target.value)} placeholder="Add a task..." />
          <button className="btn-primary" onClick={addQuick} disabled={busy}>Add</button>
        </div>
      </section>
    </div>
  )
}
