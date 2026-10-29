import { useEffect, useRef, useState } from 'react'

interface Props {
  onSend: (text: string) => void
  streaming: boolean
  onStop: () => void
}

export function Composer({ onSend, streaming, onStop }: Props) {
  const [text, setText] = useState('')
  const [attach, setAttach] = useState<File | null>(null)
  const [record, setRecord] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const ta = useRef<HTMLTextAreaElement>(null)
  const mediaRef = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const timerRef = useRef<number | null>(null)

  // auto-grow
  useEffect(() => {
    const el = ta.current
    if (!el) return
    el.style.height = 'auto'
    const max = 6 * 24
    el.style.height = Math.min(el.scrollHeight, max) + 'px'
  }, [text])

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (text.trim() || attach) {
        onSend(text.trim())
        setText('')
        setAttach(null)
      }
    }
  }

  async function onSendClick() {
    if (streaming) return
    let msg = text.trim()
    if (attach) {
      const form = new FormData()
      form.append('file', attach)
      const res = await fetch('/api/transcribe', { method: 'POST', credentials: 'include', body: form })
      if (res.ok) {
        const j = await res.json()
        if (j.text) msg = msg ? msg + ' ' + j.text : j.text
      }
    }
    onSend(msg)
    setText('')
    setAttach(null)
  }

  async function startRecording() {
    setRecord(true)
    setElapsed(0)
    chunks.current = []
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mr = new MediaRecorder(stream)
    mr.ondataavailable = (ev) => { if (ev.data.size > 0) chunks.current.push(ev.data) }
    mr.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop())
      const blob = new Blob(chunks.current, { type: mr.mimeType || 'audio/webm' })
      const form = new FormData()
      form.append('file', blob, 'audio.webm')
      const res = await fetch('/api/transcribe', { method: 'POST', credentials: 'include', body: form })
      setRecord(false)
      if (res.ok) {
        const j = await res.json()
        if (j.text) {
          setText((prev) => (prev ? prev + ' ' + j.text : j.text))
        }
      }
    }
    mediaRef.current = mr
    mr.start()
    timerRef.current = window.setInterval(() => setElapsed((n) => n + 1), 1000)
  }

  function cancelRecording() {
    try { mediaRef.current?.stop() } catch {}
    mediaRef.current = null
    chunks.current = []
    if (timerRef.current != null) { window.clearInterval(timerRef.current); timerRef.current = null }
    setRecord(false)
  }

  useEffect(() => {
    if (record && mediaRef.current && !mediaRef.current.state) {
      cancelRecording()
    }
    return () => {
      if (timerRef.current != null) { window.clearInterval(timerRef.current); timerRef.current = null }
    }
  }, [record])

  return (
    <div className="composer" style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 12px)' }}>
      <div className="composer-inner">
        <button className="icon-btn" aria-label="Attach file" onClick={() => {
          const input = document.createElement('input')
          input.type = 'file'
          input.accept = '.txt,.md,.pdf'
          input.onchange = () => setAttach(input.files?.[0] ?? null)
          input.click()
        }}>
          +
        </button>
        <textarea
          ref={ta}
          className="composer-textarea"
          rows={1}
          placeholder="Message… (Enter to send, Shift+Enter newline)"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={streaming}
        />
        {record ? (
          <div className="recording">
            REC {elapsed}s
            <button className="icon-btn danger" onClick={cancelRecording} aria-label="cancel">✕</button>
          </div>
        ) : (
          <button className="icon-btn" aria-label="Record voice" onClick={startRecording} disabled={streaming}>🎤</button>
        )}
        {streaming ? (
          <button className="icon-btn" aria-label="Stop" onClick={onStop}>■</button>
        ) : (
          <button className="icon-btn" aria-label="Send" onClick={onSendClick} disabled={!text.trim() && !attach}>➤</button>
        )}
      </div>
      {attach && <div className="attach-chip">📎 {attach.name}</div>}
    </div>
  )
}
