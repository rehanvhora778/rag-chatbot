import { useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { ArrowLeft, Info, Lock, ShieldCheck } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import AuthLayout from '../components/auth/AuthLayout'
import Brand from '../components/brand/Brand'
import { AuthCard, Field, PasswordField, Check, SubmitButton, authLink } from '../components/auth/AuthUI'

/**
 * Administrator sign-in. Same credentials as the user form, but it posts to the
 * admin endpoint, which refuses any account without staff rights — so a normal
 * user cannot reach the console by guessing this URL.
 */
export default function AdminLoginPage() {
  const { adminLogin } = useAuth()
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
    if (!form.email.trim()) err.email = 'Admin email is required'
    if (!form.password) err.password = 'Password is required'
    if (Object.keys(err).length) { setErrors(err); return }

    setLoading(true)
    try {
      await adminLogin(form.email.trim(), form.password)
      // GuestRoute takes it from here: an admin session started at /admin-login
      // lands on the console.
      toast.success('Signed in as administrator.')
    } catch (e2) {
      toast.error(e2.response?.data?.message || 'Could not sign you in. Please try again.')
      setLoading(false)
    }
  }

  return (
    <AuthLayout>
      <AuthCard>
        <Link to="/" className="mb-7 flex w-fit">
          <Brand size={30} nameSize="sm" tagline={false} id="admin-brand" />
        </Link>

        <h1 className="flex items-center gap-2 font-display text-2xl font-bold tracking-tight text-white">
          Admin Login
          <ShieldCheck size={20} className="text-primary-400" />
        </h1>
        <p className="mt-1.5 text-sm text-zinc-500">Secure access for administrators only</p>

        <div className="mt-5 flex items-start gap-2.5 rounded-xl border border-primary-500/20 bg-primary-500/[0.06] px-3.5 py-3">
          <Info size={15} className="mt-0.5 shrink-0 text-primary-400" />
          <p className="text-[13px] leading-relaxed text-zinc-400">
            This area is restricted to authorized administrators.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4" noValidate>
          <Field
            label="Admin Email"
            type="email"
            placeholder="Enter admin email"
            autoComplete="email"
            value={form.email}
            onChange={set('email')}
            error={errors.email}
          />
          <PasswordField
            placeholder="Enter admin password"
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

          <SubmitButton loading={loading} loadingLabel="Verifying…">
            <Lock size={16} /> Login as Admin
          </SubmitButton>
        </form>

        <Link
          to="/login"
          className="mt-5 flex items-center justify-center gap-1.5 text-sm font-medium text-zinc-400 transition-colors hover:text-primary-400"
        >
          <ArrowLeft size={15} /> Back to User Login
        </Link>

        <div className="mt-6 flex items-center justify-center gap-2 border-t border-white/[0.06] pt-5 text-xs text-zinc-600">
          <ShieldCheck size={13} /> Unauthorized access is strictly prohibited.
        </div>
      </AuthCard>
    </AuthLayout>
  )
}
