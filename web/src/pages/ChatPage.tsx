import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ChatShell } from '../chat/ChatShell'

export function ChatPage() {
  const auth = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (!auth.loading && !auth.user) {
      navigate(auth.needsSetup ? '/setup' : '/login', { replace: true })
    }
  }, [auth.loading, auth.user, auth.needsSetup, navigate])

  if (auth.loading) return <div className="app-shell-center muted">Loading…</div>
  if (!auth.user) return null

  const threadId = useSearchParams()[0].get('t') || 'ui-main'

  return <ChatShell threadId={threadId} />
}