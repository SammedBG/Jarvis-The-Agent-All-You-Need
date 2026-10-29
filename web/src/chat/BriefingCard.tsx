import { useEffect, useState } from 'react'
import { api, getCsrfToken } from '../lib/api'
import { ChevronDown, ChevronUp, RefreshCw, Volume2, X } from 'lucide-react'

interface Section { title: string; items: string[] }
interface Briefing { text: string; date: string; sections: Section[]; done7?: number }

export function BriefingCard() {
  const [b, setB] = useState<Briefing | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [dismissed, setDismissed] = useState(false)

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
    const key = `jarvis-briefing-dismissed-${new Date().toISOString().slice(0, 10)}`
    localStorage.setItem(key, '1')
    setDismissed(true)
    setB(null)
  }

  useEffect(() => {
    const key = `jarvis-briefing-dismissed-${new Date().toISOString().slice(0, 10)}`
    if (localStorage.getItem(key)) {
      setDismissed(true)
      return
    }
    void load()
  }, [])

  if (!b) {
    if (busy) return <div className="skeleton" />
    if (err) return <div className="error-card small"><p>{err}</p><button className="btn" onClick={load}>Retry</button></div>
    return null
  }
  const dueToday = b.sections?.filter((section) => /due today|today/i.test(section.title))
    .reduce((total, section) => total + section.items.length, 0) || 0
  const overdue = b.sections?.filter((section) => /overdue/i.test(section.title))
    .reduce((total, section) => total + section.items.length, 0) || 0
  const summary = `${dueToday} due today · ${overdue} overdue`
  const dateLabel = b.date ? new Date(b.date).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' }) : ''
  const visibleSections = b.sections?.filter((s) => s.items && s.items.length > 0) || []

  async function speak() {
    try {
      const csrf = getCsrfToken()
      const res = await fetch('/api/speak', {
        method: 'POST', credentials: 'include', headers: {
          'Content-Type': 'application/json',
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        body: JSON.stringify({ text: b?.text || '' }),
      })
      if (res.ok) {
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)
        audio.addEventListener('ended', () => URL.revokeObjectURL(url), { once: true })
        await audio.play()
      }
    } catch {}
  }

  if (dismissed) return null

  return (
    <section className="card briefing-card" aria-label="Daily briefing">
      <div className="briefing-heading">
        <div className="briefing-copy">
          <h3>Today at a glance</h3>
          <p>{dateLabel}{dateLabel ? ' · ' : ''}{summary}</p>
        </div>
        <div className="briefing-actions">
          <button className="briefing-action" title="Listen to briefing" aria-label="Listen to briefing" onClick={speak}>
            <Volume2 size={17} /><span>Listen</span>
          </button>
          <button className="briefing-action" title="Refresh briefing" aria-label="Refresh briefing" onClick={refresh} disabled={busy}>
            <RefreshCw size={16} className={busy ? 'spin' : ''} /><span>Refresh</span>
          </button>
          <button className="briefing-icon-action" title="Hide for today" aria-label="Hide briefing for today" onClick={dismiss}>
            <X size={17} />
          </button>
        </div>
      </div>
      {err && <div className="error-text">{err}</div>}
      {visibleSections.length > 0 && (
        <>
          {expanded && visibleSections.map((sec) => (
            <div key={sec.title} className="briefing-section">
              <div className="assist-title">{sec.title}</div>
              <ul className="assist-ul">
                {sec.items.map((item, index) => (
                  <li key={index} className="assist-row">{item.replace('[normal]', '').trim()}</li>
                ))}
              </ul>
            </div>
          ))}
          <button className="briefing-expand" onClick={() => setExpanded((value) => !value)}>
            {expanded ? <><ChevronUp size={15} /> Hide details</> : <><ChevronDown size={15} /> View today’s items</>}
          </button>
        </>
      )}
      {!visibleSections.length && b.text && <p className="briefing-empty">Nothing scheduled for today.</p>}
    </section>
  )
}
