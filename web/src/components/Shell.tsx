import { useState, useEffect } from 'react'
import { Sidebar } from '../chat/Sidebar'

export function Shell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < 900)

  useEffect(() => {
    const onResize = () => {
      // Keep the shell in sync when browser zoom or window resizing crosses
      // the desktop/mobile breakpoint in either direction.
      setCollapsed(window.innerWidth < 900)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  return (
    <div className="shell">
      <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />
      <div className="content">
        <button className="mobile-drawer-toggle" onClick={() => setCollapsed(false)} aria-label="open menu">≡</button>
        {children}
      </div>
    </div>
  )
}
