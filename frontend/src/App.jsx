import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext'

function Spinner() {
  return (
    <div className="flex h-[100dvh] items-center justify-center bg-ink-950">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-500/15 border-t-primary-400" />
    </div>
  )
}

// Code-split every route so the public landing page loads without pulling in
// the heavy authenticated app (charts, chat, admin).
const LandingPage    = lazy(() => import('./pages/LandingPage'))
const LoginPage      = lazy(() => import('./pages/LoginPage'))
const AdminLoginPage = lazy(() => import('./pages/AdminLoginPage'))
const RegisterPage   = lazy(() => import('./pages/RegisterPage'))
const ForgotPasswordPage = lazy(() => import('./pages/ForgotPasswordPage'))
const PrivacyPage   = lazy(() => import('./pages/PrivacyPage'))
const TermsPage     = lazy(() => import('./pages/TermsPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const DocumentsPage = lazy(() => import('./pages/DocumentsPage'))
const ChatPage      = lazy(() => import('./pages/ChatPage'))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'))
const SettingsPage  = lazy(() => import('./pages/SettingsPage'))
const AdminPage     = lazy(() => import('./pages/AdminPage'))
const ProfilePage   = lazy(() => import('./pages/ProfilePage'))
const Layout        = lazy(() => import('./components/common/Layout'))

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  return user ? children : <Navigate to="/login" replace />
}

function AdminRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user) return <Navigate to="/login" replace />
  if (!user.is_staff) return <Navigate to="/dashboard" replace />
  return children
}

function GuestRoute({ children }) {
  const { user, loading } = useAuth()
  const { pathname } = useLocation()
  if (loading) return <Spinner />
  if (!user) return children
  // Chat is the product's home screen, so signing in lands there — unless the
  // session was started from the admin door, which leads to the console.
  const target = pathname === '/admin-login' && user.is_staff ? '/admin' : '/chat'
  return <Navigate to={target} replace />
}

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/"         element={<LandingPage />} />
        <Route path="/login"    element={<GuestRoute><LoginPage /></GuestRoute>} />
        <Route path="/admin-login" element={<GuestRoute><AdminLoginPage /></GuestRoute>} />
        <Route path="/register" element={<GuestRoute><RegisterPage /></GuestRoute>} />
        <Route path="/forgot-password" element={<GuestRoute><ForgotPasswordPage /></GuestRoute>} />
        <Route path="/privacy"  element={<PrivacyPage />} />
        <Route path="/terms"    element={<TermsPage />} />

        <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
          <Route path="/dashboard"  element={<DashboardPage />} />
          <Route path="/documents"  element={<DocumentsPage />} />
          <Route path="/chat"       element={<ChatPage />} />
          <Route path="/chat/:sessionId" element={<ChatPage />} />
          <Route path="/analytics"  element={<AnalyticsPage />} />
          <Route path="/settings"   element={<SettingsPage />} />
          <Route path="/profile"    element={<ProfilePage />} />
          <Route path="/admin"      element={<AdminRoute><AdminPage /></AdminRoute>} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
