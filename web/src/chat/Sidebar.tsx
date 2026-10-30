import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from '../lib/api'

interface Conv { thread_id: string; title: string }
interface Grouped { today: Conv[]; yesterday: Conv[]; earlier: Conv[] }

export function Sidebar({ collapsed, setCollapsed }: { collapsed: boolean; setCollapsed: (v: boolean) => void }) {
  const navigate = useNavigate()
  const location = useLocation()
  const currentThread = new URLSearchParams(location.search).get('t') || 'ui-main'
  const [conversations, setConversations] = useState<Conv[]>([])

  useEffect(() => {
    let alive = true
    const load = () => {
      api.GET<Grouped>('/api/conversations?limit=100').then((groups) => {
        if (alive) setConversations([...(groups.today || []), ...(groups.yesterday || []), ...(groups.earlier || [])])
      }).catch(() => { if (alive) setConversations([]) })
    }
    load()
    window.addEventListener('jarvis:conversation-updated', load)
    return () => { alive = false; window.removeEventListener('jarvis:conversation-updated', load) }
  }, [location.pathname, location.search])

  const current = conversations.find((conversation) => conversation.thread_id === currentThread)
  const recent = conversations.filter((conversation) => conversation.thread_id !== currentThread).slice(0, 3)
  function startNewChat() {
    const now = new Date()
    const id = `ui-${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}-${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`
    navigate(`/?t=${id}`)
  }
  const nav = (path: string, label: string) => (
    <button className={`navlink${location.pathname === path ? ' active' : ''}`} onClick={() => navigate(path)}>{label}</button>
  )

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
      <button className="navbtn primary" onClick={startNewChat}>+ New chat</button>
      <div className="side-label">Chats</div>
      <button
        className={`recent-item current-chat${location.pathname === '/' ? ' active' : ''}`}
        title="Open the current chat"
        onClick={() => navigate(`/?t=${encodeURIComponent(currentThread)}`)}
      >
        <span className="current-chat-dot" aria-hidden="true" />
        <span className="chat-title">{current?.title || 'Current chat'}</span>
      </button>
      {recent.map((conversation) => (
        <button
          key={conversation.thread_id}
          className="recent-item sidebar-chat"
          title={conversation.title}
          onClick={() => navigate(`/?t=${encodeURIComponent(conversation.thread_id)}`)}
        >
          <span className="chat-title">{conversation.title}</span>
        </button>
      ))}
      <button className="all-chats-link" onClick={() => navigate('/chats')}>View all chats</button>
      <div className="side-divider" />
      <div className="side-label">Navigation</div>
      {nav('/today', 'Today')}
      {nav('/tasks', 'Tasks')}
      {nav('/settings', 'Settings')}
      <div className="side-label">Your data</div>
      {nav('/memory', 'Memory')}
      {nav('/documents', 'Documents')}
      {nav('/activity', 'Activity')}
      {nav('/usage', 'Usage')}
    </aside>
  )
}
