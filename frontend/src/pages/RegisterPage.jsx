import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
import { Eye, EyeOff, User, AtSign, Mail, Lock, ArrowRight, CheckCircle2, AlertCircle } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import AnimatedButton from '../components/ui/AnimatedButton'
import { AuthShell, Field } from '../components/landing/AuthShell'
import { cn } from '../lib/utils'

const AGREE_ERROR = 'Please accept the Terms & Privacy Policy to create your account'

const STRENGTH = ['Too short', 'Weak', 'Fair', 'Good', 'Strong']
const STRENGTH_COLOR = ['bg-zinc-300 dark:bg-white/15', 'bg-red-500', 'bg-amber-500', 'bg-sky-500', 'bg-emerald-500']

function scorePassword(pw) {
  if (!pw) return 0
  let s = 0
  if (pw.length >= 8) s++
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++
  if (/\d/.test(pw)) s++
  if (/[^A-Za-z0-9]/.test(pw)) s++
  if (pw.length < 8) return 0
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
            className={`h-1.5 flex-1 rounded-full transition-colors duration-300 ${i < score ? STRENGTH_COLOR[score] : 'bg-zinc-200 dark:bg-white/10'}`}
          />
        ))}
      </div>
      <p className="mt-1 text-xs lp-sub">
        Password strength: <span className="font-semibold lp-h">{STRENGTH[score]}</span>
      </p>
    </div>
  )
}

function RegisterSuccess({ name }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#fbfbfe] px-5 dark:bg-ink-950">
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full bg-emerald-500/15 blur-3xl" />
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
          className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-emerald-500 to-teal-600 shadow-[0_0_50px_rgba(16,185,129,0.45)]"
        >
          <CheckCircle2 size={40} className="text-white" />
        </motion.div>
        <h1 className="font-display text-3xl font-bold tracking-tight lp-h">Account created!</h1>
        <p className="mt-3 lp-sub">
          Welcome aboard{name ? `, ${name}` : ''}. Setting up your workspace…
        </p>
        <div className="mt-6 flex items-center justify-center gap-2 text-sm lp-sub">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-500/30 border-t-primary-500" />
          Redirecting to your dashboard
        </div>
      </motion.div>
    </div>
  )
}

export default function RegisterPage() {
  const { register, setUser } = useAuth()
  const [form, setForm] = useState({ fullName: '', username: '', email: '', password: '', password2: '' })
  const [showPwd, setShowPwd] = useState(false)
  const [agree, setAgree] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState({})
  const [success, setSuccess] = useState(false)
  // bumped on every failed submit so the consent row re-plays its shake
  const [agreeShake, setAgreeShake] = useState(0)

  const firstName = useMemo(() => form.fullName.trim().split(/\s+/)[0] || '', [form.fullName])

  const set = k => e => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    if (errors[k]) setErrors(p => ({ ...p, [k]: undefined }))
  }

  const validate = () => {
    const e = {}
    if (!form.fullName.trim()) e.fullName = 'Your name is required'
    if (!form.username.trim()) e.username = 'Username is required'
    else if (!/^[\w.@+-]+$/.test(form.username.trim())) e.username = 'Letters, digits and . @ + - _ only'
    if (!form.email.trim()) e.email = 'Email is required'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) e.email = 'Enter a valid email'
    if (form.password.length < 8) e.password = 'At least 8 characters'
    if (form.password !== form.password2) e.password2 = 'Passwords do not match'
    if (!agree) {
      // Easiest error on the form to overlook, so it also shakes and toasts.
      e.agree = AGREE_ERROR
      setAgreeShake(n => n + 1)
      toast.error('Please accept the Terms & Privacy Policy to continue')
    }
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleSubmit = async e => {
    e.preventDefault()
    if (!validate()) return

    const payload = {
      username: form.username.trim(),
      email: form.email.trim(),
      full_name: form.fullName.trim(),
      password: form.password,
      password2: form.password2,
    }

    setLoading(true)
    try {
      const userData = await register(payload)
      setSuccess(true)
      // let the success animation play, then commit the session → redirect
      setTimeout(() => setUser(userData), 1900)
    } catch (err) {
      const apiErrors = err.response?.data?.errors
      if (apiErrors && typeof apiErrors === 'object') {
        const mapped = {}
        Object.entries(apiErrors).forEach(([k, v]) => { mapped[k === 'full_name' ? 'fullName' : k] = Array.isArray(v) ? v[0] : String(v) })
        setErrors(prev => ({ ...prev, ...mapped }))
        Object.values(apiErrors).flat().forEach(msg => toast.error(msg))
      } else {
        toast.error(err.response?.data?.message || 'Registration failed.')
      }
      setLoading(false)
    }
  }

  if (success) return <RegisterSuccess name={firstName} />

  return (
    <AuthShell heading="Create your account" subheading="Start chatting with your documents in under a minute.">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <Field label="Full name" icon={User} placeholder="Ada Lovelace" autoComplete="name" value={form.fullName} onChange={set('fullName')} error={errors.fullName} />
        <Field label="Username" icon={AtSign} placeholder="ada" autoComplete="username" value={form.username} onChange={set('username')} error={errors.username} />
        <Field label="Email" icon={Mail} type="email" placeholder="ada@example.com" autoComplete="email" value={form.email} onChange={set('email')} error={errors.email} />
        <Field
          label="Password"
          icon={Lock}
          type={showPwd ? 'text' : 'password'}
          placeholder="At least 8 characters"
          autoComplete="new-password"
          value={form.password}
          onChange={set('password')}
          error={errors.password}
          hint={form.password ? <StrengthMeter pw={form.password} /> : null}
          rightSlot={
            <button type="button" onClick={() => setShowPwd(v => !v)} className="text-zinc-400 transition-colors hover:text-zinc-700 dark:hover:text-zinc-200" aria-label="Toggle password">
              {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          }
        />
        <Field label="Confirm password" icon={Lock} type="password" placeholder="Re-enter your password" autoComplete="new-password" value={form.password2} onChange={set('password2')} error={errors.password2} />

        <div>
          <motion.label
            key={agreeShake}
            animate={agreeShake ? { x: [0, -8, 8, -6, 6, -2, 0] } : undefined}
            transition={{ duration: 0.45, ease: 'easeInOut' }}
            className={cn(
              'flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 text-sm transition-colors duration-200 lp-sub',
              errors.agree
                ? 'border-red-500/60 bg-red-500/[0.07]'
                : 'border-transparent hover:border-zinc-200 dark:hover:border-white/10',
            )}
          >
            <input
              type="checkbox"
              checked={agree}
              onChange={e => { setAgree(e.target.checked); if (errors.agree) setErrors(p => ({ ...p, agree: undefined })) }}
              className={cn(
                'mt-0.5 h-4 w-4 rounded text-primary-600 accent-primary-600',
                errors.agree ? 'border-red-500 ring-2 ring-red-500/30' : 'border-zinc-300 dark:border-white/20',
              )}
            />
            <span>
              I agree to the{' '}
              <a href="/terms" target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} className="font-semibold text-primary-600 hover:underline dark:text-primary-400">Terms</a>{' '}and{' '}
              <a href="/privacy" target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} className="font-semibold text-primary-600 hover:underline dark:text-primary-400">Privacy Policy</a>
            </span>
          </motion.label>

          <AnimatePresence>
            {errors.agree && (
              <motion.p
                initial={{ opacity: 0, height: 0, y: -4 }}
                animate={{ opacity: 1, height: 'auto', y: 0 }}
                exit={{ opacity: 0, height: 0, y: -4 }}
                transition={{ duration: 0.2 }}
                className="flex items-start gap-1.5 overflow-hidden pl-3 pt-1.5 text-xs font-medium text-red-500"
              >
                <AlertCircle size={13} className="mt-px shrink-0" />
                {errors.agree}
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        <AnimatedButton type="submit" loading={loading} className="w-full py-3" size="lg">
          {!loading && <>Create Account <ArrowRight size={16} /></>}
          {loading && 'Creating account…'}
        </AnimatedButton>
      </form>

      <p className="mt-7 text-center text-sm lp-sub">
        Already have an account?{' '}
        <Link to="/login" className="font-semibold text-primary-600 hover:underline dark:text-primary-400">Sign in</Link>
      </p>
    </AuthShell>
  )
}
