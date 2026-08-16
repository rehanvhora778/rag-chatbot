import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'
import { KeyRound, CheckCircle2, ArrowLeft } from 'lucide-react'
import { authAPI } from '../api/auth'
import AuthLayout, { AuthAside } from '../components/auth/AuthLayout'
import { AuthCard, Field, PasswordField, SubmitButton, authLink } from '../components/auth/AuthUI'
import OtpStep from '../components/auth/OtpStep'

/**
 * Forgotten-password reset, in three steps:
 *   email    → the server emails a code (and says the same thing either way,
 *              so this page can't be used to discover which emails exist)
 *   code     → verifying it returns a short-lived ticket
 *   password → the ticket authorises the change
 */
export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState('email')
  const [email, setEmail] = useState('')
  const [meta, setMeta] = useState(null)
  const [token, setToken] = useState('')
  const [pw, setPw] = useState({ password: '', password2: '' })
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState({})
  const [otpError, setOtpError] = useState('')

  const emailValid = useMemo(() => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()), [email])

  const requestCode = async e => {
    e?.preventDefault()
    if (!emailValid) { setErrors({ email: 'Enter a valid email address' }); return }

    setLoading(true)
    try {
      const res = await authAPI.resetRequest({ email: email.trim() })
      setMeta(res.data.data)
      setStep('code')
      toast.success(res.data.message)
    } catch (err) {
      toast.error(err.response?.data?.message || 'Could not start the reset.')
    } finally {
      setLoading(false)
    }
  }

  const verifyCode = async code => {
    setOtpError('')
    setLoading(true)
    try {
      const res = await authAPI.resetVerify({ email: email.trim(), code })
      setToken(res.data.data.reset_token)
      setStep('password')
    } catch (err) {
      setOtpError(err.response?.data?.message || 'Could not verify that code.')
    } finally {
      setLoading(false)
    }
  }

  const resendCode = async () => {
    const res = await authAPI.resetRequest({ email: email.trim() })
    setOtpError('')
    toast.success('A new code is on its way.')
    return res.data.data
  }

  const savePassword = async e => {
    e.preventDefault()
    const err = {}
    if (pw.password.length < 8) err.password = 'At least 8 characters'
    if (pw.password !== pw.password2) err.password2 = 'Passwords do not match'
    if (Object.keys(err).length) { setErrors(err); return }

    setLoading(true)
    try {
      await authAPI.resetConfirm({
        email: email.trim(),
        reset_token: token,
        new_password: pw.password,
        new_password2: pw.password2,
      })
      setStep('done')
      setTimeout(() => navigate('/login', { replace: true }), 2600)
    } catch (e2) {
      const apiErrors = e2.response?.data?.errors
      if (apiErrors && typeof apiErrors === 'object') {
        const mapped = {}
        Object.entries(apiErrors).forEach(([k, v]) => {
          const key = k === 'new_password' ? 'password' : k === 'new_password2' ? 'password2' : k
          mapped[key] = Array.isArray(v) ? v[0] : String(v)
        })
        setErrors(mapped)
        Object.values(apiErrors).flat().forEach(m => toast.error(String(m)))
      } else {
        toast.error(e2.response?.data?.message || 'Could not reset your password.')
      }
      setLoading(false)
    }
  }

  const aside = {
    email:    { title: 'Forgot Password?', subtitle: 'We’ll email you a code to get you back in.' },
    code:     { title: 'Check Your Inbox',  subtitle: 'Enter the code we just sent you.' },
    password: { title: 'Almost There',      subtitle: 'Pick a new password for your account.' },
    done:     { title: 'All Set',           subtitle: 'Your password has been updated.' },
  }[step]

  return (
    <AuthLayout aside={<AuthAside title={aside.title} subtitle={aside.subtitle} />}>
      <AuthCard>
        {step === 'email' && (
          <>
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-500/[0.12] ring-1 ring-primary-500/30">
              <KeyRound size={22} className="text-primary-400" />
            </div>
            <h1 className="font-display text-2xl font-bold tracking-tight text-white">Reset your password</h1>
            <p className="mt-1.5 text-sm text-zinc-500">
              Enter the email you signed up with and we’ll send a 6-digit code.
            </p>

            <form onSubmit={requestCode} className="mt-6 space-y-4" noValidate>
              <Field
                label="Email address"
                type="email"
                placeholder="Enter your email"
                autoComplete="email"
                autoFocus
                value={email}
                onChange={e => { setEmail(e.target.value); setErrors({}) }}
                error={errors.email}
              />
              <SubmitButton loading={loading} loadingLabel="Sending code…">Send Code</SubmitButton>
            </form>

            <Link
              to="/login"
              className="mt-5 flex items-center justify-center gap-1.5 text-[13px] text-zinc-500 transition-colors hover:text-primary-400"
            >
              <ArrowLeft size={14} /> Back to login
            </Link>
          </>
        )}

        {step === 'code' && (
          <OtpStep
            email={email.trim()}
            onVerify={verifyCode}
            onResend={resendCode}
            onBack={() => { setStep('email'); setOtpError('') }}
            backLabel="Use a different email"
            title="Enter your reset code"
            submitLabel="Verify Code"
            loading={loading}
            error={otpError}
            resendAfter={meta?.resend_after_seconds}
          />
        )}

        {step === 'password' && (
          <motion.div
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            <h1 className="font-display text-2xl font-bold tracking-tight text-white">Choose a new password</h1>
            <p className="mt-1.5 text-sm text-zinc-500">
              Signing in with the old one will stop working right away.
            </p>

            <form onSubmit={savePassword} className="mt-6 space-y-4" noValidate>
              <PasswordField
                label="New Password"
                placeholder="Create a new password"
                autoComplete="new-password"
                autoFocus
                value={pw.password}
                onChange={e => { setPw(p => ({ ...p, password: e.target.value })); setErrors({}) }}
                error={errors.password}
              />
              <PasswordField
                label="Confirm New Password"
                placeholder="Repeat the new password"
                autoComplete="new-password"
                value={pw.password2}
                onChange={e => { setPw(p => ({ ...p, password2: e.target.value })); setErrors({}) }}
                error={errors.password2}
              />
              <SubmitButton loading={loading} loadingLabel="Updating…">Update Password</SubmitButton>
            </form>
          </motion.div>
        )}

        {step === 'done' && (
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            className="py-4 text-center"
          >
            <motion.div
              initial={{ scale: 0, rotate: -40 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ type: 'spring', stiffness: 220, damping: 16, delay: 0.1 }}
              className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-primary-300 to-primary-600 shadow-glow-lg"
            >
              <CheckCircle2 size={32} className="text-ink-950" />
            </motion.div>
            <h1 className="font-display text-2xl font-bold tracking-tight text-white">Password updated</h1>
            <p className="mt-2 text-sm text-zinc-500">Taking you to the login page…</p>
            <Link to="/login" className={`mt-5 inline-block text-sm ${authLink}`}>Login now</Link>
          </motion.div>
        )}
      </AuthCard>
    </AuthLayout>
  )
}
