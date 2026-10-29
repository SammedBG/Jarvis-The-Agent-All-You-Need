const API_BASE = '' // same origin via Vite proxy or FastAPI static

let csrfToken: string | null = null
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn
}

export function getCsrfToken() {
  return csrfToken
}

export async function fetchMe(): Promise<{ id: number; username: string; csrf_token: string } | null> {
  try {
    const res = await fetch(`${API_BASE}/api/me`, { credentials: 'include' })
    if (!res.ok) return null
    const data = await res.json()
    csrfToken = data.csrf_token ?? null
    return data
  } catch {
    return null
  }
}

export function clearCsrf() {
  csrfToken = null
}

export interface ApiError extends Error {
  status?: number
  body?: any
}

async function request<T>(method: string, path: string, body?: any): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (csrfToken && method !== 'GET') headers['X-CSRF-Token'] = csrfToken
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      credentials: 'include',
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    const err = new Error('Network error - check your connection') as ApiError
    err.status = 0
    throw err
  }
  if (res.status === 401) {
    onUnauthorized?.()
    const err = new Error('Not authenticated') as ApiError
    err.status = 401
    throw err
  }
  if (!res.ok) {
    let body: any = null
    try { body = await res.json() } catch { /* not json */ }
    const err = new Error(body?.detail || `Error ${res.status}`) as ApiError
    err.status = res.status
    err.body = body
    throw err
  }
  if (res.status === 204) return undefined as T
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return (await res.json()) as T
  return (await res.text()) as T
}

export const api = {
  GET: <T>(path: string) => request<T>('GET', path),
  POST: <T>(path: string, body?: any) => request<T>('POST', path, body),
  PATCH: <T>(path: string, body?: any) => request<T>('PATCH', path, body),
  PUT: <T>(path: string, body?: any) => request<T>('PUT', path, body),
  DELETE: <T>(path: string, body?: any) => request<T>('DELETE', path, body),
}