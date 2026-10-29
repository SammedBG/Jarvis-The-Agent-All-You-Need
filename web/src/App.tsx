import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { SetupPage } from './pages/SetupPage'
import { LoginPage } from './pages/LoginPage'
import { ChatPage } from './pages/ChatPage'
import { TodayPage } from './pages/TodayPage'
import { TasksPage } from './pages/TasksPage'
import { SettingsPage } from './pages/SettingsPage'
import { Shell } from './components/Shell'

function Protected() {
  const auth = useAuth()
  if (auth.loading) return <div className="app-shell-center muted">Loading…</div>
  if (!auth.user) return <Navigate to={auth.needsSetup ? '/setup' : '/login'} replace />
  return (
    <Shell>
      <Outlet />
    </Shell>
  )
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/setup" element={<SetupPage />} />
      <Route element={<Protected />}>
        <Route path="/" element={<ChatPage />} />
        <Route path="/today" element={<TodayPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}

export default App