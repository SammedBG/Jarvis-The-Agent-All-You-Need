import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api } from '../lib/api'

const VIEWS = ['pending', 'today', 'overdue', 'week', 'all']

export function TasksPage() {
  const auth = useAuth()
  const [view, setView] = useState('pending')
  const [result, setResult] = useState('')

  useEffect(() => {
    if (!auth.loading && auth.user) load(view)
  }, [auth.loading, auth.user, view])

  async function load(v: string) {
    const r: any = await api.GET(`/api/tasks?view=${v}`)
    setResult(r?.text || '')
  }

  async function markDone(taskText: string) { if (!taskText) return
    // extract #id from "Task #3: ..."
    const m = taskText.match(/#(\d+)/)
    if (!m) return
    await api.PATCH(`/api/tasks/${m[1]}`, { status: 'done' })
    await load(view)
  }

  async function snooze(taskText: string) { if (!taskText) return
    const m = taskText.match(/#(\d+)/)
    if (!m) return
    await api.PATCH(`/api/tasks/${m[1]}`, { minutes: 60 })
    await load(view)
  }

  async function cancel(taskText: string) { if (!taskText) return
    const m = taskText.match(/#(\d+)/)
    if (!m) return
    await api.DELETE(`/api/tasks/${m[1]}`)
    await load(view)
  }

  void (markDone); void (snooze); void (cancel)
  return (
    <div className="page">
      <h2>Tasks</h2>
      <div className="filter-row">
        {VIEWS.map((v) => (
          <button key={v} className={v === view ? 'chip chip-active' : 'chip'} onClick={() => setView(v)}>{v}</button>
        ))}
      </div>
      <pre className="task-text">{result}</pre>
      <div className="muted small">Use the API: PATCH /api/tasks/id to update.</div>
    </div>
  )
}
