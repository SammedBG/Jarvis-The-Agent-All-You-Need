import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'

interface Conversation { thread_id: string; title: string }
interface Groups { today: Conversation[]; yesterday: Conversation[]; earlier: Conversation[] }

export function ChatsPage() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [chats, setChats] = useState<Conversation[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const groups = await api.GET<Groups>('/api/conversations?limit=500')
      setChats([...(groups.today || []), ...(groups.yesterday || []), ...(groups.earlier || [])])
      setError('')
    } catch (e: any) {
      setError(e?.message || 'Could not load chats.')
    }
  }, [])

  useEffect(() => { if (!auth.loading && auth.user) void load() }, [auth.loading, auth.user, load])

  async function rename(chat: Conversation) {
    const title = window.prompt('Rename chat', chat.title)?.trim()
    if (!title || title === chat.title) return
    try {
      await api.PATCH(`/api/conversations/${encodeURIComponent(chat.thread_id)}`, { title })
      await load()
      window.dispatchEvent(new Event('jarvis:conversation-updated'))
    } catch (e: any) { setError(e?.message || 'Could not rename chat.') }
  }

  async function remove(chat: Conversation) {
    if (!window.confirm(`Delete “${chat.title}”? This cannot be undone.`)) return
    try {
      await api.DELETE(`/api/conversations/${encodeURIComponent(chat.thread_id)}`)
      await load()
      window.dispatchEvent(new Event('jarvis:conversation-updated'))
    } catch (e: any) { setError(e?.message || 'Could not delete chat.') }
  }

  function newChat() {
    const now = new Date()
    const id = `ui-${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}-${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`
    navigate(`/?t=${id}`)
  }

  const visible = chats.filter((chat) => chat.title.toLowerCase().includes(query.toLowerCase()))
  if (!auth.user) return <div className="app-shell-center muted">Loading chats…</div>

  return (
    <div className="page chats-page">
      <header className="page-heading">
        <div><h2>Your chats</h2><p className="muted small">Open, search, or rename a previous conversation.</p></div>
        <button className="btn-primary chats-new" onClick={newChat}>+ New chat</button>
      </header>
      {error && <div className="error-card">{error}</div>}
      <input className="input chats-search" placeholder="Search chat titles…" value={query} onChange={(e) => setQuery(e.target.value)} />
      {visible.length === 0 ? <p className="muted chats-empty">No saved chats found.</p> : (
        <div className="chats-list">
          {visible.map((chat) => (
            <article className="chat-list-card" key={chat.thread_id}>
              <button className="chat-list-open" onClick={() => navigate(`/?t=${encodeURIComponent(chat.thread_id)}`)}>
                <span className="chat-list-title">{chat.title}</span>
                <span className="chat-list-id">{chat.thread_id}</span>
              </button>
              <div className="chat-list-actions">
                <button className="btn-secondary" onClick={() => void rename(chat)}>Rename</button>
                <button className="btn-secondary danger-text" onClick={() => void remove(chat)}>Delete</button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
