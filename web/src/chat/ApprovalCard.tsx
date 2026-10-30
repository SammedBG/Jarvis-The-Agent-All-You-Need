interface Approval {
  id: string
  tool: string
  exact_args: any
  reason: string
  origin?: string
}

export function ApprovalCard({ approval, onApprove, onDecline }: {
  approval: Approval
  onApprove: () => void
  onDecline: () => void
}) {
  const argsText = JSON.stringify(approval.exact_args, null, 2)
  return (
    <div className="approval-card" role="alertdialog" aria-modal="false">
      <div className="approval-title">I need your approval first</div>
      <div className="approval-tool"><span className="monospace">{approval.tool}</span></div>
      <div className="approval-label">Exact arguments:</div>
      <pre className="approval-args" tabIndex={0}>{argsText}</pre>
      <div className="approval-label">Reason:</div>
      <div className="approval-reason">{approval.reason}</div>
      {approval.origin && (
        <div className="approval-label muted">Source of request: <code>{approval.origin}</code></div>
      )}
      <p className="muted small">Nothing will run until you click Approve.</p>
      <div className="dialog-row">
        <button className="btn btn-primary wide" onClick={onApprove}>Approve</button>
        <button className="btn btn-secondary wide" onClick={onDecline}>Decline</button>
      </div>
    </div>
  )
}
