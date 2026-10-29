import { useEffect, useRef, useState } from 'react'
import { getCsrfToken } from '../lib/api'
import { FileUp, Mic, Send, Square, X } from 'lucide-react'

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
  const [busy, setBusy] = useState(false)
  const [processingVoice, setProcessingVoice] = useState(false)
  const [voiceError, setVoiceError] = useState('')
  const ta = useRef<HTMLTextAreaElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const mediaRef = useRef<MediaRecorder | null>(null)
  const cancelRef = useRef(false)
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
        void onSendClick()
      }
    }
  }

  async function onSendClick() {
    if (streaming || busy || record) return
    let msg = text.trim()
    if (attach) {
      setBusy(true)
      try {
        const form = new FormData()
        form.append('file', attach)
        const csrf = getCsrfToken()
        const res = await fetch('/api/documents/extract', {
          method: 'POST', credentials: 'include',
          headers: csrf ? { 'X-CSRF-Token': csrf } : {}, body: form,
        })
        const document = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(document.detail || `Could not read document (${res.status})`)
        const question = msg || 'Please review and summarize this document.'
        msg = `${question}\n\n[Attached document: ${document.filename}]\n${document.text}`
      } catch (error: any) {
        setVoiceError(error?.message || 'Could not attach this document.')
        setBusy(false)
        return
      }
      setBusy(false)
    }
    if (!msg.trim()) return
    onSend(msg)
    setText('')
    setAttach(null)
  }

  async function startRecording() {
    setVoiceError('')
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setVoiceError('Voice recording is not supported by this browser.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      cancelRef.current = false
      setElapsed(0)
      chunks.current = []
      mr.ondataavailable = (ev) => { if (ev.data.size > 0) chunks.current.push(ev.data) }
      mr.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop())
        mediaRef.current = null
        if (timerRef.current != null) { window.clearInterval(timerRef.current); timerRef.current = null }
        setRecord(false)
        if (cancelRef.current) {
          chunks.current = []
          setBusy(false)
          setProcessingVoice(false)
          return
        }
        const blob = new Blob(chunks.current, { type: mr.mimeType || 'audio/webm' })
        chunks.current = []
        if (!blob.size) {
          setVoiceError('No audio was recorded. Try again.')
          setBusy(false)
          setProcessingVoice(false)
          return
        }
        setBusy(true)
        setProcessingVoice(true)
        try {
          const form = new FormData()
          form.append('file', blob, 'audio.webm')
          const csrf = getCsrfToken()
          const res = await fetch('/api/transcribe', {
            method: 'POST', credentials: 'include',
            headers: csrf ? { 'X-CSRF-Token': csrf } : {}, body: form,
          })
          const result = await res.json().catch(() => ({}))
          if (!res.ok) throw new Error(result.detail || `Transcription failed (${res.status})`)
          if (!result.text) throw new Error('No speech was detected. Try recording again.')
          setText((prev) => (prev ? `${prev} ${result.text}` : result.text))
        } catch (error: any) {
          setVoiceError(error?.message || 'Voice transcription failed.')
        } finally {
          setBusy(false)
          setProcessingVoice(false)
        }
      }
      mediaRef.current = mr
      mr.start()
      setRecord(true)
      timerRef.current = window.setInterval(() => setElapsed((n) => n + 1), 1000)
    } catch {
      setVoiceError('Microphone permission was denied or no microphone is available.')
    }
  }

  function finishRecording() {
    if (mediaRef.current?.state === 'recording') {
      setBusy(true)
      setProcessingVoice(true)
      mediaRef.current.stop()
    }
  }

  function cancelRecording() {
    cancelRef.current = true
    try { mediaRef.current?.stop() } catch { /* recorder already stopped */ }
    if (!mediaRef.current) setRecord(false)
    chunks.current = []
    if (timerRef.current != null) { window.clearInterval(timerRef.current); timerRef.current = null }
    setRecord(false)
    setBusy(false)
    setProcessingVoice(false)
  }

  useEffect(() => () => {
    cancelRef.current = true
    try { mediaRef.current?.stop() } catch { /* recorder already stopped */ }
    if (timerRef.current != null) window.clearInterval(timerRef.current)
  }, [])

  return (
    <div className="composer" style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 12px)' }}>
      <div className="composer-inner">
        <button className="icon-btn" aria-label="Attach document" title="Attach a PDF, text, or Markdown document" onClick={() => fileInput.current?.click()} disabled={streaming || busy}>
          <FileUp size={18} strokeWidth={1.8} />
        </button>
        <input ref={fileInput} className="composer-file-input" type="file" accept=".txt,.md,.pdf" onChange={(event) => { setAttach(event.target.files?.[0] ?? null); event.currentTarget.value = ''; setVoiceError('') }} />
        {record ? (
          <div className="voice-capture" role="status" aria-live="polite">
            <button className="voice-cancel" onClick={cancelRecording} aria-label="Cancel recording" title="Discard recording"><X size={18} /></button>
            <div className="voice-live">
              <span className="voice-live-label"><span className="recording-dot" />Listening</span>
              <span className="voice-wave" aria-hidden="true">{Array.from({ length: 24 }, (_, index) => <i key={index} />)}</span>
              <span className="voice-time">{String(Math.floor(elapsed / 60)).padStart(2, '0')}:{String(elapsed % 60).padStart(2, '0')}</span>
            </div>
            <button className="voice-finish" onClick={finishRecording} aria-label="Finish voice input" title="Finish and transcribe" disabled={busy}><Square size={15} fill="currentColor" /></button>
          </div>
        ) : (
          <textarea
            ref={ta}
            className="composer-textarea"
            rows={1}
            placeholder={processingVoice ? 'Transcribing your voice…' : 'Message JARVIS…'}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={streaming || busy}
          />
        )}
        {!record && (
          <button className="icon-btn" aria-label="Dictate a message" title="Dictate a message" onClick={startRecording} disabled={streaming || busy}>
            <Mic size={18} strokeWidth={1.8} />
          </button>
        )}
        {record ? null : streaming ? (
          <button className="icon-btn" aria-label="Stop response" onClick={onStop}><Square size={17} /></button>
        ) : (
          <button className="icon-btn send-btn" aria-label="Send" title="Send message" onClick={onSendClick} disabled={busy || record || (!text.trim() && !attach)}>
            <Send size={18} />
          </button>
        )}
      </div>
      {attach && <div className="attach-chip"><FileUp size={14} /> <span>{attach.name}</span><button onClick={() => setAttach(null)} aria-label="Remove attachment"><X size={14} /></button></div>}
      {busy && !processingVoice && attach && <div className="composer-status">Reading document…</div>}
      {voiceError && <div className="composer-status composer-error" role="status">{voiceError}</div>}
    </div>
  )
}
