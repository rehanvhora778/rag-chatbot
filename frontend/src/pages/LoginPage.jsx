import { useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Lock, ShieldCheck } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import AuthLayout, { AuthAside } from '../components/auth/AuthLayout'
import { AuthCard, Field, PasswordField, Check, SubmitButton, authLink } from '../components/auth/AuthUI'
import { SocialRow } from '../components/auth/SocialAuth'

export default function LoginPage() {
  const { login, googleLogin } = useAuth()
  const [form, setForm] = useState({ email: '', password: '' })
  const [remember, setRemember] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState({})

  const set = k => e => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    if (errors[k]) setErrors(p => ({ ...p, [k]: undefined }))
  }

  const handleSubmit = async e => {
    e.preventDefault()
    const err = {}
    if (!form.email.trim()) err.email = 'Email address is required'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) err.email = 'Enter a valid email address'
    if (!form.password) err.password = 'Password is required'
    if (Object.keys(err).length) { setErrors(err); return }

    setLoading(true)
    try {
      await login(form.email.trim(), form.password)
      toast.success('Welcome back!')
    } catch (e2) {
      toast.error(e2.response?.data?.message || 'Could not sign you in. Please try again.')
      setLoading(false)
    }
  }

  const handleGoogle = async credential => {
    setLoading(true)
    try {
      await googleLogin(credential)
      toast.success('Welcome back!')
    } catch (e2) {
      toast.error(e2.response?.data?.message || 'Google sign-in failed.')
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      aside={<AuthAside title="Welcome Back!" subtitle="Login to continue your RAG journey." />}
    >
      <AuthCard>
        <h1 className="font-display text-2xl font-bold tracking-tight text-white">User Login</h1>
        <p className="mt-1.5 text-sm text-zinc-500">Enter your credentials to access your account</p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
          <Field
            label="Email address"
            type="email"
            placeholder="Enter your email"
            autoComplete="email"
            value={form.email}
            onChange={set('email')}
            error={errors.email}
          />
          <PasswordField
            placeholder="Enter your password"
            autoComplete="current-password"
            value={form.password}
            onChange={set('password')}
            error={errors.password}
          />

          <div className="flex items-center justify-between pt-0.5">
            <Check checked={remember} onChange={setRemember}>Remember me</Check>
            <Link to="/forgot-password" className={`text-[13px] ${authLink}`}>
              Forgot password?
            </Link>
          </div>

          <SubmitButton loading={loading} loadingLabel="Signing in…">Login</SubmitButton>
        </form>

        <SocialRow onCredential={handleGoogle} disabled={loading} />

        <p className="mt-6 text-center text-sm text-zinc-500">
          Don&apos;t have an account? <Link to="/register" className={authLink}>Register</Link>
        </p>
      </AuthCard>

      {/* admin door — deliberately separate from the user form */}
      <div className="mt-4 flex flex-col items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/[0.02] px-5 py-3.5 text-sm sm:flex-row">
        <span className="flex items-center gap-2 text-zinc-500">
          <Lock size={14} /> Admin access?
        </span>
        <Link to="/admin-login" className={`inline-flex items-center gap-1.5 ${authLink}`}>
          <ShieldCheck size={15} /> Login as Admin
        </Link>
      </div>
    </AuthLayout>
  )
}
