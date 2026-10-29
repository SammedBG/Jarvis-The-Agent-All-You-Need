import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'

interface Fact { id: number; text: string; source: string; origin?: string }
interface Rule { id: number; text: string }

export function MemoryPage() {
  const auth = useAuth()
  const [facts, setFacts] = useState<Fact[]>([])
  const [rules, setRules] = useState<Rule[]>([])
  const [newFact, setNewFact] = useState('')
  const [newRule, setNewRule] = useState('')
  const [editingFact, setEditingFact] = useState<number | null>(null)
  const [editingRule, setEditingRule] = useState<number | null>(null)
  const [editFactText, setEditFactText] = useState('')
  const [editRuleText, setEditRuleText] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!auth.loading && auth.user) { loadFacts(); loadRules() }
  }, [auth.loading, auth.user])

  async function loadFacts() {
    try {
      const d: any = await api.GET('/api/memory/facts')
      setFacts((d?.facts || []).map((f: any) => ({ id: f.id, text: f.text, source: f.source, origin: f.origin })))
    } catch (e: any) { setErr(e?.message || 'Failed to load facts') }
  }
  async function loadRules() {
    try {
      const d: any = await api.GET('/api/memory/rules')
      setRules((d?.rules || []).map((r: any) => ({ id: r.id, text: r.text })))
    } catch (e: any) { setErr(e?.message || 'Failed to load rules') }
  }

  async function addFact() {
    if (!newFact.trim()) return
    setErr(''); setMsg('')
    try {
      await api.POST('/api/memory/facts', { text: newFact.trim(), source: 'user' })
      setNewFact('')
      await loadFacts()
      setMsg('Fact saved.')
    } catch (e: any) { setErr(e?.message || 'Add fact failed') }
  }
  async function addRule() {
    if (!newRule.trim()) return
    setErr(''); setMsg('')
    try {
      await api.POST('/api/memory/rules', { text: newRule.trim() })
      setNewRule('')
      await loadRules()
      setMsg('Rule saved.')
    } catch (e: any) { setErr(e?.message || 'Add rule failed') }
  }
  async function saveFact(id: number) {
    setErr(''); setMsg('')
    try {
      await api.PATCH(`/api/memory/facts/${id}`, { text: editFactText.trim() })
      setEditingFact(null)
      await loadFacts()
      setMsg('Fact updated.')
    } catch (e: any) { setErr(e?.message || 'Update fact failed') }
  }
  async function saveRule(id: number) {
    setErr(''); setMsg('')
    try {
      await api.PATCH(`/api/memory/rules/${id}`, { text: editRuleText.trim() })
      setEditingRule(null)
      await loadRules()
      setMsg('Rule updated.')
    } catch (e: any) { setErr(e?.message || 'Update rule failed') }
  }
  async function delFact(id: number) {
    if (!window.confirm('Delete this fact permanently?')) return
    setErr(''); setMsg('')
    try {
      await api.DELETE(`/api/memory/facts/${id}`)
      await loadFacts()
      setMsg('Fact deleted.')
    } catch (e: any) { setErr(e?.message || 'Delete fact failed') }
  }
  async function delRule(id: number) {
    if (!window.confirm('Delete this rule permanently?')) return
    setErr(''); setMsg('')
    try {
      await api.DELETE(`/api/memory/rules/${id}`)
      await loadRules()
      setMsg('Rule deleted.')
    } catch (e: any) { setErr(e?.message || 'Delete rule failed') }
  }

  if (!auth.user) return <div className="app-shell-center muted">Loading memory…</div>

  return (
    <div className="page">
      <h2>Long-term memory</h2>
      <p className="muted small">Lasting facts about you and standing rules the agent follows. Stored locally in SQLite.</p>
      {err && <div className="error-text">{err}</div>}
      {msg && <div className="ok-text">{msg}</div>}

      <section className="card">
        <h3>Remembered facts</h3>
        <div className="dialog-row">
          <input className="input" placeholder="e.g. I prefer brief answers" value={newFact} onChange={(e) => setNewFact(e.target.value)} />
          <button className="btn-primary" onClick={addFact}>Add fact</button>
        </div>
        {facts.length === 0 ? <p className="muted small">No facts saved yet.</p> : (
          <ul className="list">
            {facts.map((f) => (
              <li key={f.id} className="list-item">
                {editingFact === f.id ? (
                  <>
                    <input className="input" autoFocus value={editFactText} onChange={(e) => setEditFactText(e.target.value)} />
                    <button className="btn btn-secondary" onClick={() => saveFact(f.id)}>Save</button>
                    <button className="btn btn-secondary" onClick={() => setEditingFact(null)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <span className="fact-text">{f.text}</span>
                    <span className="muted small">({f.source}{f.origin ? ` · ${f.origin}` : ''})</span>
                    <button className="btn-link" onClick={() => { setEditFactText(f.text); setEditingFact(f.id) }}>Edit</button>
                    <button className="btn-link" onClick={() => delFact(f.id)}>Delete</button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h3>Standing rules</h3>
        <p className="muted small">Restrictions and preferences the agent must never break (e.g. "never suggest alcohol").</p>
        <div className="dialog-row">
          <input className="input" placeholder="e.g. Never suggest spending money" value={newRule} onChange={(e) => setNewRule(e.target.value)} />
          <button className="btn-primary" onClick={addRule}>Add rule</button>
        </div>
        {rules.length === 0 ? <p className="muted small">No rules saved yet.</p> : (
          <ul className="list">
            {rules.map((r) => (
              <li key={r.id} className="list-item">
                {editingRule === r.id ? (
                  <>
                    <input className="input" autoFocus value={editRuleText} onChange={(e) => setEditRuleText(e.target.value)} />
                    <button className="btn btn-secondary" onClick={() => saveRule(r.id)}>Save</button>
                    <button className="btn btn-secondary" onClick={() => setEditingRule(null)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <span className="rule-text">{r.text}</span>
                    <button className="btn-link" onClick={() => { setEditRuleText(r.text); setEditingRule(r.id) }}>Edit</button>
                    <button className="btn-link" onClick={() => delRule(r.id)}>Delete</button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
