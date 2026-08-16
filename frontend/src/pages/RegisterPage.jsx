import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'
import { CheckCircle2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import AuthLayout, { AuthAside } from '../components/auth/AuthLayout'
import { AuthCard, Field, PasswordField, Check, SubmitButton, authLink } from '../components/auth/AuthUI'
import { SocialRow } from '../components/auth/SocialAuth'
import OtpStep from '../components/auth/OtpStep'

const STRENGTH = ['Too short', 'Weak', 'Fair', 'Good', 'Strong']
const STRENGTH_COLOR = ['bg-white/15', 'bg-red-500', 'bg-amber-500', 'bg-sky-500', 'bg-emerald-500']

function scorePassword(pw) {
  if (!pw || pw.length < 8) return 0
  let s = 0
  if (pw.length >= 8) s++
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++
  if (/\d/.test(pw)) s++
  if (/[^A-Za-z0-9]/.test(pw)) s++
  return s
}

function StrengthMeter({ pw }) {
  const score = scorePassword(pw)
  return (
    <div>
      <div className="flex gap-1.5">
        {[0, 1, 2, 3].map(i => (
          <span
            key={i}
            className={`h-1.5 flex-1 rounded-full transition-colors duration-300 ${i < score ? STRENGTH_COLOR[score] : 'bg-white/10'}`}
          />
        ))}
      </div>
      <p className="mt-1 text-xs text-zinc-500">
        Password strength: <span className="font-semibold text-zinc-300">{STRENGTH[score]}</span>
      </p>
    </div>
  )
}

function RegisterSuccess({ name }) {
  return (
    <div className="relative flex min-h-[100dvh] items-center justify-center overflow-hidden bg-ink-950 px-5">
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary-500/15 blur-3xl" />
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="relative z-10 w-full max-w-md text-center"
      >
        <motion.div
          initial={{ scale: 0, rotate: -40 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: 'spring', stiffness: 220, damping: 16, delay: 0.15 }}
          className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-primary-300 to-primary-600 shadow-glow-lg"
        >
          <CheckCircle2 size={40} className="text-ink-950" />
        </motion.div>
        <h1 className="font-display text-3xl font-bold tracking-tight text-white">Account created!</h1>
        <p className="mt-3 text-zinc-400">
          Welcome aboard{name ? `, ${name}` : ''}. Setting up your workspace…
        </p>
        <div className="mt-6 flex items-center justify-center gap-2 text-sm text-zinc-500">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-500/30 border-t-primary-500" />
          Taking you to your chat
        </div>
      </motion.div>
    </div>
  )
}

export default function RegisterPage() {
  const { register, resendRegisterCode, verifyRegistration, googleLogin, setUser } = useAuth()
  const [form, setForm] = useState({ fullName: '', email: '', password: '', password2: '' })
  const [agree, setAgree] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState({})
  const [success, setSuccess] = useState(false)
  // 'form' → fill in details, 'otp' → prove the email address is real.
  const [step, setStep] = useState('form')
  const [pending, setPending] = useState(null)   // { email, resend_after_seconds }
  const [otpError, setOtpError] = useState('')

  const firstName = useMemo(() => form.fullName.trim().split(/\s+/)[0] || '', [form.fullName])

  const set = k => e => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    if (errors[k]) setErrors(p => ({ ...p, [k]: undefined }))
  }

  const validate = () => {
    const e = {}
    if (!form.fullName.trim()) e.fullName = 'Your name is required'
    if (!form.email.trim()) e.email = 'Email is required'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) e.email = 'Enter a valid email address'
    if (form.password.length < 8) e.password = 'At least 8 characters'
    if (form.password !== form.password2) e.password2 = 'Passwords do not match'
    if (!agree) {
      e.agree = true
      toast.error('Please accept the Terms of Service and Privacy Policy to continue.')
    }
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleSubmit = async e => {
    e.preventDefault()
    if (!validate()) return

    setLoading(true)
    try {
      // Nothing is created yet — this only sends the code to the address given.
      const meta = await register({
        full_name: form.fullName.trim(),
        email: form.email.trim(),
        password: form.password,
        password2: form.password2,
      })
      setPending(meta)
      setStep('otp')
      toast.success('Verification code sent — check your email.')
    } catch (err) {
      const apiErrors = err.response?.data?.errors
      if (apiErrors && typeof apiErrors === 'object') {
        const mapped = {}
        Object.entries(apiErrors).forEach(([k, v]) => {
          mapped[k === 'full_name' ? 'fullName' : k] = Array.isArray(v) ? v[0] : String(v)
        })
        setErrors(prev => ({ ...prev, ...mapped }))
        Object.values(apiErrors).flat().forEach(msg => toast.error(String(msg)))
      } else {
        toast.error(err.response?.data?.message || 'Registration failed.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleVerify = async code => {
    setOtpError('')
    setLoading(true)
    try {
      const userData = await verifyRegistration(pending.email, code)
      setSuccess(true)
      // let the success animation play, then commit the session → redirect
      setTimeout(() => setUser(userData), 1900)
    } catch (err) {
      setOtpError(err.response?.data?.message || 'Could not verify that code.')
      setLoading(false)
    }
  }

  const handleResend = async () => {
    try {
      const meta = await resendRegisterCode(pending.email)
      setOtpError('')
      toast.success('A new code is on its way.')
      return meta
    } catch (err) {
      toast.error(err.response?.data?.message || 'Could not resend the code.')
      throw err
    }
  }

  const handleGoogle = async credential => {
    setLoading(true)
    try {
      const data = await googleLogin(credential)
      toast.success(data.created ? 'Account created with Google!' : 'Welcome back!')
    } catch (e2) {
      toast.error(e2.response?.data?.message || 'Google sign-up failed.')
      setLoading(false)
    }
  }

  if (success) return <RegisterSuccess name={firstName} />

  if (step === 'otp') {
    return (
      <AuthLayout
        aside={
          <AuthAside
            title="One Last Step"
            subtitle="Confirm your email address and your workspace is ready."
          />
        }
      >
        <AuthCard>
          <OtpStep
            email={pending.email}
            onVerify={handleVerify}
            onResend={handleResend}
            onBack={() => { setStep('form'); setOtpError(''); setPending(null) }}
            backLabel="Use a different email"
            title="Verify your email"
            submitLabel="Verify & Create Account"
            loadingLabel="Creating account…"
            loading={loading}
            error={otpError}
            resendAfter={pending.resend_after_seconds}
          />
        </AuthCard>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      aside={
        <AuthAside
          title="Start Your Journey"
          subtitle="Create an account and put your documents to work."
        />
      }
    >
      <AuthCard>
        <h1 className="font-display text-2xl font-bold tracking-tight text-white">Create Your Account</h1>
        <p className="mt-1.5 text-sm text-zinc-500">Fill in the details to get started</p>

        <form onSubmit={handleSubmit} className="mt-5 space-y-3.5" noValidate>
          <Field
            label="Full Name"
            placeholder="Enter your full name"
            autoComplete="name"
            value={form.fullName}
            onChange={set('fullName')}
            error={errors.fullName}
          />
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
            placeholder="Create a password"
            autoComplete="new-password"
            value={form.password}
            onChange={set('password')}
            error={errors.password}
            hint={form.password ? <StrengthMeter pw={form.password} /> : null}
          />
          <PasswordField
            label="Confirm Password"
            placeholder="Confirm your password"
            autoComplete="new-password"
            value={form.password2}
            onChange={set('password2')}
            error={errors.password2}
          />

          <Check
            checked={agree}
            onChange={v => { setAgree(v); if (errors.agree) setErrors(p => ({ ...p, agree: undefined })) }}
            error={errors.agree}
          >
            I agree to the{' '}
            <Link to="/terms" target="_blank" className={authLink}>Terms of Service</Link> and{' '}
            <Link to="/privacy" target="_blank" className={authLink}>Privacy Policy</Link>
          </Check>

          <SubmitButton loading={loading} loadingLabel="Creating account…">Create Account</SubmitButton>
        </form>

        <SocialRow onCredential={handleGoogle} disabled={loading} />

        <p className="mt-5 text-center text-sm text-zinc-500">
          Already have an account? <Link to="/login" className={authLink}>Login</Link>
        </p>
      </AuthCard>
    </AuthLayout>
  )
}
