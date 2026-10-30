import { useEffect, useRef, useState } from 'react'
import { getCsrfToken } from '../lib/api'
import { FileUp, Mic, MicOff, Send, Square, X } from 'lucide-react'

interface Props {
  onSend: (text: string) => void
  onVoiceSend: (text: string) => void
  streaming: boolean
  onStop: () => void
  voiceMode: boolean
  voicePaused: boolean
  onVoiceModeChange: (enabled: boolean) => void
}

export function Composer({ onSend, onVoiceSend, streaming, onStop, voiceMode, voicePaused, onVoiceModeChange }: Props) {
  const [text, setText] = useState('')
  const [attach, setAttach] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [voiceError, setVoiceError] = useState('')
  const [voiceListening, setVoiceListening] = useState(false)
  const [voiceTranscript, setVoiceTranscript] = useState('')
  const ta = useRef<HTMLTextAreaElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const onVoiceSendRef = useRef(onVoiceSend)
  const pausedRef = useRef(voicePaused)

  useEffect(() => { onVoiceSendRef.current = onVoiceSend }, [onVoiceSend])
  useEffect(() => { pausedRef.current = voicePaused }, [voicePaused])

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
    if (streaming || busy) return
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

  async function toggleVoiceMode() {
    setVoiceError('')
    if (voiceMode) {
      onVoiceModeChange(false)
      return
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setVoiceError('Microphone access requires a secure browser context such as localhost or HTTPS.')
      return
    }
    try {
      // Request permission directly from the click gesture. It is then retained
      // while hands-free recognition runs, without another click per turn.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((track) => track.stop())
      onVoiceModeChange(true)
    } catch {
      setVoiceError('Microphone permission was denied. Allow microphone access, then enable voice mode again.')
    }
  }

  useEffect(() => {
    if (!voiceMode) {
      setVoiceListening(false)
      setVoiceTranscript('')
      return
    }
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      setVoiceError('Hands-free voice requires Chrome or Edge. Voice mode was turned off.')
      onVoiceModeChange(false)
      return
    }

    let live = true
    let restartTimer: number | undefined
    let sendTimer: number | undefined
    let pendingText = ''
    let recognition: any
    const start = () => {
      if (!live || pausedRef.current || !recognition) return
      try { recognition.start() } catch { /* already starting/listening */ }
    }
    recognition = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = navigator.language || 'en-US'
    recognition.onstart = () => { if (live) setVoiceListening(true) }
    recognition.onresult = (event: any) => {
      let interim = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index]
        const phrase = result[0]?.transcript?.trim()
        if (!phrase) continue
        if (result.isFinal) pendingText = `${pendingText} ${phrase}`.trim()
        else interim = `${interim} ${phrase}`.trim()
      }
      setVoiceTranscript([pendingText, interim].filter(Boolean).join(' '))
      if (pendingText) {
        if (sendTimer) window.clearTimeout(sendTimer)
        sendTimer = window.setTimeout(() => {
          const message = pendingText.trim()
          pendingText = ''
          setVoiceTranscript('')
          if (message && live && !pausedRef.current) onVoiceSendRef.current(message)
        }, 900)
      }
    }
    recognition.onerror = (event: any) => {
      if (!live || event.error === 'no-speech' || event.error === 'aborted') return
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        setVoiceError('Microphone permission is blocked. Allow microphone access in your browser, then enable voice mode again.')
        onVoiceModeChange(false)
      } else {
        setVoiceError(`Voice recognition error: ${event.error || 'unknown error'}`)
      }
    }
    recognition.onend = () => {
      if (!live) return
      setVoiceListening(false)
      if (!pausedRef.current) restartTimer = window.setTimeout(start, 300)
    }
    start()
    return () => {
      live = false
      if (restartTimer) window.clearTimeout(restartTimer)
      if (sendTimer) window.clearTimeout(sendTimer)
      try { recognition.stop() } catch { /* already stopped */ }
      setVoiceListening(false)
    }
  }, [voiceMode, voicePaused, onVoiceModeChange])

  return (
    <div className="composer" style={{ paddingBottom: 'calc(env(safe-area-inset-bottom) + 12px)' }}>
      <div className="composer-inner">
        <button className="icon-btn" aria-label="Attach document" title="Attach a PDF, text, or Markdown document" onClick={() => fileInput.current?.click()} disabled={streaming || busy}>
          <FileUp size={18} strokeWidth={1.8} />
        </button>
        <input ref={fileInput} className="composer-file-input" type="file" accept=".txt,.md,.pdf" onChange={(event) => { setAttach(event.target.files?.[0] ?? null); event.currentTarget.value = ''; setVoiceError('') }} />
        {voiceMode ? (
          <div className="voice-capture" role="status" aria-live="polite">
            <div className="voice-live">
              <span className="voice-live-label"><span className="recording-dot" />{voicePaused ? 'JARVIS responding' : voiceListening ? 'Listening' : 'Starting microphone'}</span>
              <span className="voice-wave" aria-hidden="true">{Array.from({ length: 24 }, (_, index) => <i key={index} />)}</span>
              <span className="voice-transcript">{voiceTranscript || 'Speak naturally; JARVIS will reply aloud.'}</span>
            </div>
          </div>
        ) : (
          <textarea
            ref={ta}
            className="composer-textarea"
            rows={1}
            placeholder="Message JARVIS…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={streaming || busy}
          />
        )}
        <button
          className={`icon-btn voice-mode-toggle${voiceMode ? ' active' : ''}`}
          aria-label={voiceMode ? 'Turn off hands-free voice mode' : 'Turn on hands-free voice mode'}
          title={voiceMode ? 'Turn off hands-free voice mode' : 'Turn on hands-free voice mode'}
          onClick={() => { void toggleVoiceMode() }}
        >
          {voiceMode ? <MicOff size={18} strokeWidth={1.8} /> : <Mic size={18} strokeWidth={1.8} />}
        </button>
        {streaming && !voiceMode ? (
          <button className="icon-btn" aria-label="Stop response" onClick={onStop}><Square size={17} /></button>
        ) : !voiceMode && (
          streaming ? null : <button className="icon-btn send-btn" aria-label="Send" title="Send message" onClick={onSendClick} disabled={busy || (!text.trim() && !attach)}>
            <Send size={18} />
          </button>
        )}
      </div>
      {attach && <div className="attach-chip"><FileUp size={14} /> <span>{attach.name}</span><button onClick={() => setAttach(null)} aria-label="Remove attachment"><X size={14} /></button></div>}
      {busy && attach && <div className="composer-status">Reading document…</div>}
      {voiceError && <div className="composer-status composer-error" role="status">{voiceError}</div>}
    </div>
  )
}
