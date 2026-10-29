import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { api, getCsrfToken } from '../lib/api'

export function DocumentsPage() {
  const auth = useAuth()
  const [docs, setDocs] = useState<string[]>([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [searchResults, setSearchResults] = useState<Array<{ source: string; page: string | number | null; score: number; text: string }>>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [uploading, setUploading] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const [indexExists, setIndexExists] = useState(false)

  useEffect(() => {
    if (!auth.loading && auth.user) load()
  }, [auth.loading, auth.user])

  async function load() {
    setErr(''); setMsg('')
    try {
      const d: any = await api.GET('/api/documents')
      setDocs(d.documents || [])
      setIndexExists(!!d.index_exists)
    } catch (e: any) {
      setErr(e?.message || 'Failed to load documents')
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setErr('')
    try {
      const form = new FormData()
      form.append('file', file)
      const headers: Record<string, string> = {}
      const csrf = getCsrfToken()
      if (csrf) headers['X-CSRF-Token'] = csrf
      const res = await fetch('/api/documents/upload', {
        method: 'POST',
        credentials: 'include',
        headers,
        body: form,
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail || `Upload failed ${res.status}`)
      }
      setMsg(`Uploaded '${file.name}'. Reindex to make it searchable.`)
      e.target.value = ''
      await load()
    } catch (err: any) {
      setErr(err?.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function handleSearch() {
    if (!searchQuery.trim()) return
    setErr('')
    try {
      const d: any = await api.GET(`/api/documents/search?q=${encodeURIComponent(searchQuery)}&k=5`)
      setSearchResults(d.results || [])
    } catch (err: any) {
      setErr(err?.message || 'Search failed')
    }
  }

  async function handleReindex() {
    setReindexing(true)
    setErr('')
    try {
      const d: any = await api.POST('/api/documents/reindex', {})
      setMsg(`Reindexed: ${d.files} files, ${d.chunks} chunks${d.skipped?.length ? ` (skipped: ${d.skipped.join(', ')})` : ''}.`)
      await load()
    } catch (err: any) {
      setErr(err?.message || 'Reindex failed')
    } finally {
      setReindexing(false)
    }
  }

  async function handleDelete(filename: string) {
    if (!confirm(`Delete '${filename}'?`)) return
    setErr('')
    try {
      await api.DELETE(`/api/documents/${encodeURIComponent(filename)}`)
      setMsg(`Deleted '${filename}'.`)
      await load()
    } catch (err: any) {
      setErr(err?.message || 'Delete failed')
    }
  }

  if (!auth.user) return <div className="app-shell-center muted">Loading documents…</div>

  return (
    <div className="page">
      <h2>Documents</h2>
      <p className="muted small">RAG document index — upload, list, and search your own files (PDFs, text, docs/ folder).</p>
      {err && <div className="error-text">{err}</div>}
      {msg && <div className="ok-text">{msg}</div>}

      <section className="card">
        <h3>Available documents</h3>
        <div className="muted small">
          {indexExists ? 'Search index ready' : 'No search index yet — upload files, then click Reindex.'}
        </div>
        {docs.length === 0 ? (
          <p className="muted small">No documents indexed yet.</p>
        ) : (
          <ul className="list">
            {docs.map((d) => (
              <li key={d} className="list-item">
                {d}
                <button className="btn btn-secondary btn-small" onClick={() => handleDelete(d)} title="Delete">🗑</button>
              </li>
            ))}
          </ul>
        )}
        <div className="dialog-row" style={{ marginTop: 10 }}>
          <input
            className="input"
            type="file"
            accept=".txt,.md,.pdf"
            onChange={handleUpload}
            disabled={uploading}
          />
          {uploading && <span className="muted small"> uploading…</span>}
        </div>
      </section>

      <section className="card">
        <h3>Search documents</h3>
        <div className="dialog-row">
          <input
            className="input"
            placeholder="Search your documents…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
          />
          <button className="btn btn-primary" onClick={handleSearch} disabled={!searchQuery.trim()}>
            Search
          </button>
        </div>
        {searchResults.length > 0 && (
          <ul className="list">
            {searchResults.map((r, i) => (
              <li key={i} className="list-item">
                <strong>{r.source}{r.page ? ` (p${r.page})` : ''}</strong> — score {r.score}
                <p className="muted small">{r.text}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h3>Index</h3>
        <button
          className="btn btn-primary"
          onClick={handleReindex}
          disabled={reindexing}
        >
          {reindexing ? 'Reindexing…' : 'Rebuild search index'}
        </button>
        <p className="muted small">
          Runs server-side indexing: reads docs/, embeds with fastembed
          (BAAI/bge-small-en-v1.5), saves to rag_index/.
        </p>
      </section>
    </div>
  )
}
