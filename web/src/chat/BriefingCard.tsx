import { useEffect, useState } from 'react'
import { api } from '../lib/api'

interface Section { title: string; items: string[] }
interface Briefing { text: string; date: string; sections: Section[]; done7?: number }

export function BriefingCard() {
  const [b, setB] = useState<Briefing | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function load() {
    setBusy(true)
    setErr('')
    try { setB(await api.GET('/api/briefing')) } catch (e: any) { setErr(e?.message || 'Failed to load') }
    setBusy(false)
  }
  async function refresh() {
    setBusy(true)
    setErr('')
    try { setB(await api.POST('/api/briefing/refresh', {})) } catch (e: any) { setErr(e?.message || 'Failed to refresh') }
    setBusy(false)
  }
  async function dismiss() {
    try { await api.POST('/api/settings', { home_location: '' }) } catch {}
    setB(null)
  }

  useEffect(() => { load() }, [])

  if (!b) {
    if (busy) return <div className="skeleton" />
    if (err) return <div className="error-card small"><p>{err}</p><button className="btn" onClick={load}>Retry</button></div>
    return null
  }
  const tasks = b.sections?.reduce((acc, s) => acc + s.items.length, 0) || 0
  const summary = `${tasks} due today - 0 overdue`
  const dateLabel = b.date ? new Date(b.date).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' }) : ''
  const visibleSections = b.sections?.filter((s) => s.items && s.items.length > 0) || []

  async function speak() {
    try {
      const res = await fetch('/api/speak', {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': (window as any).__csrf || '' },
        body: JSON.stringify({ text: b?.text || '' }),
      })
      if (res.ok) {
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)
        audio.play()
      }
    } catch {}
  }

  return (
    <div className="card briefing-card">
      <h3>Daily briefing</h3>
      {dateLabel && <div className="muted small">{dateLabel}</div>}
      <div className="muted small">{summary}</div>
      <div className="dialog-row push">
        <button className="btn btn-secondary" title="Play briefing" onClick={speak}>Play</button>
        <button className="btn btn-secondary" title="Refresh" onClick={refresh} disabled={busy}>{busy ? '…' : 'Refresh'}</button>
        <button className="btn btn-secondary" title="Dismiss for today" onClick={dismiss}>Dismiss for today</button>
      </div>
      {err && <div className="error-text">{err}</div>}
      {b.text && visibleSections.length === 0 && !busy && <div className="muted small auto-collapse">Nothing due today</div>}
      <details open={expanded} onToggle={(e) => setExpanded((e.target as any).open)}>
        <summary className="hidden-details-summary">{expanded ? 'Collapse' : ''}</summary>
        {b.text && visibleSections.length === 0 && expanded === false ? null : null}
      </details>
      {expanded && (
        <>
          {visibleSections.map((sec) => (
            <div key={sec.title} className="assist-block">
              <div className="assist-title">{sec.title}</div>
              <ul className="assist-ul">
                {sec.items.map((it, i) => (
                  <li key={i} className="assist-row">
                    <input type="checkbox" className="assist-check" aria-label="done" />
                    <span>{it.replace('[normal]', '').trim()}</span>
                    <span className="muted small time">{(it.match(/\d{1,2}:\d{2}\s*(?:am|pm)?/i) || [''])[0]}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {!expanded && null}
        </>
      )}
      {b.done7 ? <div className="muted small">Completed in the last 7 days: {b.done7}</div> : null}
    </div>
  )
}
