import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { streamSSE } from '../lib/sse'
import { ApprovalCard } from './ApprovalCard'
import { Composer } from './Composer'
import { MarkdownMessage } from './MarkdownMessage'
import { BriefingCard } from './BriefingCard'

export interface ChatMsg {
  id: string
  role: 'user' | 'assistant'
  content: string
  tools?: string[]
  usage?: { route: string; prompt_tokens: number; completion_tokens: number; latency_ms: number }
  error?: string | null
  approval?: any
}

interface ToolStep { name: string; status: 'running' | 'done' | 'error'; ms?: number }

export function ChatShell({ threadId }: { threadId: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [tools, setTools] = useState<ToolStep[]>([])
  const [approval, setApproval] = useState<any | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [errorCard, setErrorCard] = useState<string | null>(null)
  const [usageLine, setUsageLine] = useState<string | null>(null)
  const [needLocCard, setNeedLocCard] = useState(false)
  const [locInput, setLocInput] = useState('')
  const [locLink, setLocLink] = useState('')
  const lastUserRef = useRef<string>('')
  const [locBusy, setLocBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const autoScroll = useRef(true)

  const appendMessage = useCallback((m: ChatMsg) => setMessages((prev) => [...prev, m]), [])
  const updateLastAssistant = useCallback((updater: (m: ChatMsg) => ChatMsg) => {
    setMessages((prev) => {
      const next = [...prev]
      const idx = next.length - 1
      if (idx >= 0 && next[idx].role === 'assistant') next[idx] = updater(next[idx])
      return next
    })
  }, [])

  const send = useCallback(async (text: string) => {
    if (!text.trim() || streaming) return
    lastUserRef.current = text
    setNeedLocCard(false)
    setErrorCard(null)
    setStreaming(true)
    setTools([])
    setUsageLine(null)
    setApproval(null)
    appendMessage({ id: crypto.randomUUID(), role: 'user', content: text })
    appendMessage({ id: crypto.randomUUID(), role: 'assistant', content: '' })

    let accumulated = ''
    let rafId: number | null = null
    const flush = (force = false) => {
      if (rafId != null && !force) return
      rafId = null
      updateLastAssistant((m) => ({ ...m, content: accumulated }))
    }
    const controller = new AbortController()

    // store controller so stop can abort
    ;(window as any).__chat_abort = controller

    try {
      await streamSSE('/api/chat', { thread_id: threadId, message: text }, (ev) => {
        if (ev.type === 'token') {
          accumulated += ev.text || ''
          if (rafId == null) {
            rafId = requestAnimationFrame(() => { flush(true) })
          }
        } else if (ev.type === 'tool_start') {
          setTools((t) => [...t, { name: ev.name, status: 'running' }])
        } else if (ev.type === 'tool_end') {
          setTools((t) => t.map((s) => s.name === ev.name ? { ...s, status: ev.status === 'error' ? 'error' : 'done' } : s))
        } else if (ev.type === 'approval_required') {
          setApproval(ev)
        } else if (ev.type === 'usage') {
          setUsageLine(`${ev.route || 'route'} · ${ev.prompt_tokens + ev.completion_tokens} tok · ${ev.latency_ms}ms`)
        } else if (ev.type === 'error') {
          setErrorCard(ev.message || 'Something went wrong.')
        } else if (ev.type === 'done') {
          flush(true)
        }
      }, controller.signal)
    } catch (e: any) {
      setErrorCard(e?.message || 'Something went wrong.')
    } finally {
      flush(true)
      setStreaming(false)
      ;(window as any).__chat_abort = null
      const needsLoc = /which area and city/i.test(accumulated) || /no location saved/i.test(accumulated)
      if (needsLoc) setNeedLocCard(true)
    }
  }, [threadId, streaming, appendMessage, updateLastAssistant])

  const stop = useCallback(() => {
    try { api.POST('/api/chat/stop', { thread_id: threadId }) } catch {}
    const c = (window as any).__chat_abort as AbortController | null
    c?.abort()
  }, [threadId])

  const approve = useCallback(async (approved: boolean) => {
    if (!approval) return
    setErrorCard(null)
    const id = approval.id
    const feedback = approved ? '' : 'declined'
    // send only the id; exact args come from server
    try {
      await api.POST('/api/approve', { id, approved, thread_id: threadId, feedback })
    } catch (e: any) {
      setErrorCard(e?.message || 'Approval failed')
    } finally {
      setApproval(null)
    }
  }, [approval, threadId])

  // auto scroll
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => {
      const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
      autoScroll.current = nearBottom
    }
    el.addEventListener('scroll', onScroll)
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    if (autoScroll.current) {
      const el = scrollRef.current
      if (el) el.scrollTop = el.scrollHeight
    }
  }, [messages, tools, streaming])

  async function saveLocLabel(label: string) {
    if (!label.trim()) return
    setLocBusy(true)
    try {
      await api.POST('/api/settings/location', { label })
      setNeedLocCard(false)
      setLocInput('')
      const orig = lastUserRef.current
      if (orig) send(orig)
    } catch (e: any) {}
    setLocBusy(false)
  }

  function allowGeo() {
    if (!navigator.geolocation) {
      setErrorCard('Geolocation not supported on this device/browser; please enter an area and city or paste a Maps link.')
      return
    }
    navigator.geolocation.getCurrentPosition(async (pos) => {
      setLocBusy(true)
      try {
        const lat = pos.coords.latitude
        const lon = pos.coords.longitude
        await api.POST('/api/settings/location', { lat, lon })
        setNeedLocCard(false)
        const orig = lastUserRef.current
        if (orig) send(orig)
      } catch (e: any) {}
      setLocBusy(false)
    }, () => {
      setErrorCard('Permission denied or geolocation unavailable (needs localhost/HTTPS). Enter an area/city or paste a Maps link.')
    }, { enableHighAccuracy: false })
  }

  const suggestions = ['Plan my day', 'Nearest veg restaurant', 'Add a task', 'What can you do?']

  return (
    <div className="chat-shell">
      <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 && (
          <>
            <h1 className="greeting">Good morning</h1>
            {false && <div className="time-check" />}
            <BriefingCard />
            <div className="chips">
              {suggestions.map((s) => (
                <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </>
        )}

        {messages.map((m, i) => (
          <div key={m.id} className={`message ${m.role}`}>
            {m.role === 'assistant' && <span className="avatar">✳</span>}
            <div className="msg-body">
              {m.role === 'assistant' ? (
                <>
                  {m.content ? <MarkdownMessage content={m.content} /> : (i === messages.length - 1 && streaming ? <span className="typing">✳</span> : null)}
                  {i === messages.length - 1 && tools.length > 0 && (
                    <details className="tools-chip">
                      <summary>Used {tools.length} tools</summary>
                      <ul>
                        {tools.map((t, j) => (
                          <li key={j} className={t.status}>• {t.name}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                  {i === messages.length - 1 && usageLine && <div className="usage-line">{usageLine}</div>}
                </>
              ) : (
                <div className="bubble">{m.content}</div>
              )}
            </div>
          </div>
        ))}

        {approval && (
          <ApprovalCard approval={approval} onApprove={() => approve(true)} onDecline={() => approve(false)} />
        )}

        {streaming && errorCard === null && (
          <div className="typing-row"><span className="typing">✳</span> thinking…</div>
        )}

        {errorCard && (
          <div className="error-card">
            <p>{errorCard}</p>
            <button className="btn" onClick={() => setErrorCard(null)}>Retry</button>
          </div>
        )}
      </div>

      {!autoScroll.current && (
        <button className="jump-to-latest" onClick={() => { if (scrollRef.current) { scrollRef.current.scrollTop = scrollRef.current.scrollHeight; autoScroll.current = true } }}>
          Jump to latest
        </button>
      )}

      {needLocCard && (
        <div className="location-card">
          <div className="approval-label">Location needed</div>
          <p className="muted small">Where are you currently located? Pick one:</p>
          <div className="dialog-row">
            <button className="btn btn-primary" onClick={allowGeo} disabled={locBusy}>Allow location</button>
            <input className="input" placeholder="area + city, e.g. Indiranagar, Bengaluru" value={locInput} onChange={(e) => setLocInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') saveLocLabel(locInput) }} />
            <button className="btn btn-secondary" onClick={() => saveLocLabel(locInput)} disabled={locBusy || !locInput.trim()}>Use area/city</button>
          </div>
          <div className="dialog-row">
            <input className="input" placeholder="Paste Google Maps link or lat, lon" value={locLink} onChange={(e) => setLocLink(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') saveLocLabel(locLink) }} />
            <button className="btn btn-secondary" onClick={() => saveLocLabel(locLink)} disabled={locBusy || !locLink.trim()}>Use link/coords</button>
          </div>
        </div>
      )}
      <Composer onSend={send} streaming={streaming} onStop={stop} />
    </div>
  )
}
