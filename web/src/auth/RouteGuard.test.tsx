import { render, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { App } from '../App'

vi.mock('../lib/api', () => ({
  fetchMe: async () => null,
  api: { GET: async () => null, POST: async () => ({}) , PATCH: async () => ({}), DELETE: async () => ({}) },
  getCsrfToken: () => null,
  setUnauthorizedHandler: () => {},
}))

describe('Route guard', () => {
  it('redirects unauthenticated / to /login', async () => {
    vi.stubGlobal('fetch', async (input: any) => {
      if (String(input).includes('/api/auth/setup')) {
        return { ok: false, status: 403, clone: () => ({ json: async () => ({ detail: 'auth already configured' }) }), json: async () => ({ detail: 'auth already configured' }) }
      }
      return { ok: false, status: 401, json: async () => ({ detail: 'not authenticated' }) }
    })
    render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>)
    await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
    expect(screen.getByText('Sign in to continue.')).toBeInTheDocument()
  })
})
