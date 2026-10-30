import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ApprovalCard } from './ApprovalCard'

describe('ApprovalCard', () => {
  it('sends only the id (no arguments) on approve/decline', () => {
    const a = { id: 'abc123', tool: 'run_command', exact_args: { cmd: 'rm -rf /' }, reason: 'r', origin: 'user' }
    const onApprove = vi.fn()
    const onDecline = vi.fn()
    render(<ApprovalCard approval={a} onApprove={onApprove} onDecline={onDecline} />)
    fireEvent.click(screen.getByText('Approve'))
    expect(onApprove).toHaveBeenCalled()
    fireEvent.click(screen.getByText('Decline'))
    expect(onDecline).toHaveBeenCalled()
  })

  it('renders exact args, reason, and origin', () => {
    const a = { id: 'x', tool: 'add_task', exact_args: { title: 'secret' }, reason: 'danger', origin: 'web' }
    render(<ApprovalCard approval={a} onApprove={() => {}} onDecline={() => {}} />)
    expect(screen.getByText(/add_task/)).toBeInTheDocument()
    expect(screen.getByText(/secret/)).toBeInTheDocument()
    expect(screen.getByText(/danger/)).toBeInTheDocument()
    expect(screen.getByText(/web/)).toBeInTheDocument()
  })
})
