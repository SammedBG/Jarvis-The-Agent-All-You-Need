import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

interface Conv { thread_id: string; title: string }
interface Grouped { today: Conv[]; yesterday: Conv[]; earlier: Conv[] }

export function Sidebar({ collapsed, setCollapsed }: { collapsed: boolean; setCollapsed: (v: boolean) => void }) {
  const navigate = useNavigate()
  const [groups, setGroups] = useState<Grouped>({ today: [], yesterday: [], earlier: [] })
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])

  async function loadRecents() {
    try {
      const data = await api.GET<Grouped>('/api/conversations')
      setGroups(data)
    } catch {}
  }
  async function search(q: string) {
    if (!q.trim()) { setResults([]); return }
    try {
      const data = await api.GET<{ results: any[] }>(`/api/search?q=${encodeURIComponent(q)}`)
      setResults(data.results || [])
    } catch { setResults([]) }
  }

  useEffect(() => { loadRecents() }, [])

  if (collapsed) {
    return (
      <aside className="sidebar collapsed">
        <button className="icon-btn" onClick={() => setCollapsed(false)} aria-label="expand">≡</button>
      </aside>
    )
  }

  return (
    <aside className="sidebar">
      <button className="icon-btn close" onClick={() => setCollapsed(true)} aria-label="hide">≡</button>
      <div className="brand">JARVIS</div>
      <button className="navbtn primary" onClick={() => navigate('/')}>+ New chat</button>
      <div className="side-label">Search chats</div>
      <input className="input-search" placeholder="Search conversations…" value={query} onChange={(e) => { setQuery(e.target.value); search(e.target.value) }} />
      {query && results.length > 0 && (
        <div className="search-results">
          {results.map((r) => (
            <button key={r.thread_id} className="recent-item" onClick={() => navigate(`/chat/${r.thread_id}`)}>
              • {r.snippet?.slice(0, 50)}
            </button>
          ))}
        </div>
      )}
      {results.length === 0 && !query && (
        <>
          <div className="side-label">Recents</div>
          {['Today', 'Yesterday', 'Earlier'].map((name, i) => {
            const arr = [groups.today, groups.yesterday, groups.earlier][i]
            if (!arr.length) return null
            return (
              <div key={name}>
                <div className="side-sub">{name}</div>
                {arr.slice(0, 5).map((c) => (
                  <button key={c.thread_id} className="recent-item" onClick={() => navigate(`/chat/${c.thread_id}`)}>
                    {c.title}
                  </button>
                ))}
              </div>
            )
          })}
        </>
      )}
      <div className="side-divider" />
      <div className="side-label">Navigation</div>
      <button className="navlink" onClick={() => navigate('/')}>Chat</button>
      <button className="navlink" onClick={() => navigate('/today')}>Today</button>
      <button className="navlink" onClick={() => navigate('/tasks')}>Tasks</button>
      <button className="navlink" onClick={() => navigate('/settings')}>Settings</button>
      <div className="side-label">Your data</div>
      <button className="navlink" onClick={() => navigate('/memory')}>Memory</button>
      <button className="navlink" onClick={() => navigate('/documents')}>Documents</button>
      <button className="navlink" onClick={() => navigate('/activity')}>Activity</button>
      <button className="navlink" onClick={() => navigate('/usage')}>Usage</button>
    </aside>
  )
}
