import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'

export function SettingsPage() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [s, setS] = useState<any>(null)
  const [loc, setLoc] = useState('')
  const [mc, setMc] = useState('')
  const [ms, setMs] = useState('')
  const [cap, setCap] = useState(200000)
  const [aliases, setAliases] = useState('')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    if (!auth.loading && !auth.user) navigate('/login', { replace: true })
    if (!auth.loading && auth.user) load()
  }, [auth.loading, auth.user, navigate])

  async function load() {
    try { const d: any = await api.GET('/api/settings'); setS(d); setLoc(d?.home_location || ''); setMc(d?.model_complex || ''); setMs(d?.model_simple || ''); setCap(d?.groq_daily_token_cap || 200000); setAliases(d?.fast_path_aliases || '') } catch (e: any) { setMsg(e?.message || 'Failed') }
  }

  async function save() {
    setMsg('')
    try {
      await api.PATCH('/api/settings', {
        model_complex: mc, model_simple: ms, groq_daily_token_cap: cap,
        fast_path_aliases: aliases, home_location: s?.home_location,
      })
      await load()
      setMsg('Saved.')
    } catch (e: any) { setMsg(e?.message || 'Save failed') }
  }

  async function saveLocation() {
    try {
      await api.POST('/api/settings/location', { label: loc })
      setMsg('Location saved.')
      await load()
    } catch (e: any) { setMsg(e?.message || 'Geocode failed') }
  }

  async function clearLocation() {
    try { await api.DELETE('/api/settings/location'); setLoc(''); await load(); setMsg('Cleared.') } catch (e: any) { setMsg(e?.message || 'Failed') }
  }

  async function useGeo() {
    if (!navigator.geolocation) { setMsg('Geolocation not supported on this device/browser.'); return }
    navigator.geolocation.getCurrentPosition(async (pos) => {
      try {
        await api.POST('/api/settings/location', { lat: pos.coords.latitude, lon: pos.coords.longitude })
        setMsg('Location saved as "Current location".')
        await load()
      } catch (e: any) { setMsg(e?.message || 'Save failed') }
    }, () => { setMsg('Permission denied, or geolocation unavailable (HTTPS/localhost required).') }, { enableHighAccuracy: false })
  }

  async function testKey(provider: string) {
    try {
      const r: any = await api.POST('/api/settings/test_key', { provider })
      setMsg(`${provider}: ${r.status} - ${r.detail}`)
    } catch (e: any) { setMsg(e?.message || 'Failed') }
  }

  async function changePassword() {
    const newPw = prompt('New password (min 12 chars):')
    if (!newPw || newPw.length < 12) { setMsg('Password must be at least 12 chars.'); return }
    const u = auth.user?.username
    if (!u) return
    // no change-password endpoint yet; use manage.py (CLI) or reset-password
    setMsg('Use the CLI: python manage.py reset-password ' + u)
  }

  async function signOutEverywhere() {
    try { await api.POST('/api/auth/logout-all', {}) } catch (e) { /* ignore */ }
    auth.refresh()
  }

  if (!s) return <div className="app-shell-center muted">Loading settings…</div>

  return (
    <div className="page">
      <h2>Settings</h2>
      <section className="card">
        <h3>Home location (for ‘find nearby places’)</h3>
        {s.home_location && <p className="muted small">Saved: {(() => {
          try { const j = JSON.parse(s.home_location); return `${j.label} (${Number(j.lat).toFixed(2)}, ${Number(j.lon).toFixed(2)})` } catch { return s.home_location }
        })()}</p>}
        {!s.home_location && <p className="muted small">No location saved — set one below.</p>}
        <p className="muted small">Tip: paste an address/city, a Google Maps link, or lat, lon.</p>
        <input className="input" placeholder="e.g. Marine Drive, Mumbai" value={loc} onChange={(e) => setLoc(e.target.value)} />
        <div className="dialog-row">
          <button className="btn-primary" onClick={saveLocation}>Save location</button>
          <button className="btn btn-secondary" onClick={useGeo}>Use my current location</button>
          <button className="btn btn-secondary" onClick={clearLocation}>Clear</button>
        </div>
      </section>
      <section className="card">
        <h3>Models</h3>
        <label className="label">Complex model</label>
        <input className="input" value={mc} onChange={(e) => setMc(e.target.value)} placeholder="groq:openai/gpt-oss-120b" />
        <label className="label">Simple model</label>
        <input className="input" value={ms} onChange={(e) => setMs(e.target.value)} placeholder="groq:openai/gpt-oss-20b" />
        <label className="label">Daily token limit</label>
        <input className="input" type="number" value={cap} onChange={(e) => setCap(parseInt(e.target.value || '0', 10))} />
        <button className="btn-primary" onClick={() => save()}>Save models & cap</button>
      </section>
      <section className="card">
        <h3>API key status (never shown)</h3>
        <ul className="key-status">
          <li>Groq: <strong>{s.api_keys?.groq ? 'Set' : 'Not set'}</strong> <button className="btn-link" onClick={() => testKey('groq')}>Test</button></li>
          <li>Google Places: <strong>{s.api_keys?.google ? 'Set' : 'Not set'}</strong> <button className="btn-link" onClick={() => testKey('google')}>Test</button></li>
          <li>Foursquare: <strong>{s.api_keys?.foursquare ? 'Set' : 'Not set'}</strong> <button className="btn-link" onClick={() => testKey('foursquare')}>Test</button></li>
          <li>Gmail IMAP: <strong>{s.api_keys?.gmail ? 'Set' : 'Not set'}</strong> <button className="btn-link" onClick={() => testKey('gmail')}>Test</button></li>
        </ul>
        <p className="muted small">Add keys in `.env` then restart the backend.</p>
      </section>
      <section className="card">
        <h3>Fast-path alias whitelist</h3>
        <textarea className="input" rows={8} value={aliases} onChange={(e) => setAliases(e.target.value)} placeholder="chrome -> google-chrome" />
        <button className="btn-primary" onClick={save}>Save aliases</button>
      </section>
      <section className="card">
        <h3>Account</h3>
        <div className="dialog-row">
          <button className="btn-secondary" onClick={changePassword}>Change password (CLI)</button>
          <button className="btn-secondary" onClick={signOutEverywhere}>Sign out everywhere</button>
        </div>
        {msg && <div className="error-text">{msg}</div>}
      </section>
    </div>
  )
}
