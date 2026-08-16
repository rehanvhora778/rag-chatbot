import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { MailCheck, ArrowLeft } from 'lucide-react'
import OtpInput from './OtpInput'
import { SubmitButton, authLink } from './AuthUI'

/**
 * The "enter the code we emailed you" screen, shared by sign-up and password
 * reset. It owns the code field and the resend countdown; the parent owns what
 * verifying actually does.
 */
export default function OtpStep({
  email,
  onVerify,
  onResend,
  onBack,
  backLabel = 'Use a different email',
  title = 'Check your email',
  submitLabel = 'Verify',
  loadingLabel = 'Verifying…',
  loading = false,
  error = '',
  resendAfter = 60,
}) {
  const [code, setCode] = useState('')
  const [seconds, setSeconds] = useState(resendAfter)
  const [resending, setResending] = useState(false)

  useEffect(() => {
    if (seconds <= 0) return
    const t = setInterval(() => setSeconds(s => (s <= 1 ? 0 : s - 1)), 1000)
    return () => clearInterval(t)
  }, [seconds])

  // A wrong code should leave the boxes ready to retype rather than half-full.
  useEffect(() => { if (error) setCode('') }, [error])

  const submit = (e) => {
    e?.preventDefault()
    if (code.length === 6 && !loading) onVerify(code)
  }

  const resend = async () => {
    if (seconds > 0 || resending) return
    setResending(true)
    try {
      const meta = await onResend()
      setSeconds(meta?.resend_after_seconds || resendAfter)
      setCode('')
    } catch {
      // The parent toasts the reason (rate limit, mail failure); keep the
      // countdown at zero so another try is possible.
    } finally {
      setResending(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-500/[0.12] ring-1 ring-primary-500/30">
        <MailCheck size={22} className="text-primary-400" />
      </div>

      <h1 className="font-display text-2xl font-bold tracking-tight text-white">{title}</h1>
      <p className="mt-1.5 text-sm leading-relaxed text-zinc-500">
        We sent a 6-digit code to{' '}
        <span className="font-semibold text-zinc-300">{email}</span>. It expires in 10 minutes.
      </p>

      <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
        <OtpInput
          value={code}
          onChange={setCode}
          onComplete={c => !loading && onVerify(c)}
          disabled={loading}
          error={!!error}
        />

        {error && <p className="text-center text-xs font-medium text-red-400">{error}</p>}

        <SubmitButton loading={loading} loadingLabel={loadingLabel} disabled={loading || code.length < 6}>
          {submitLabel}
        </SubmitButton>
      </form>

      <p className="mt-5 text-center text-sm text-zinc-500">
        Didn&apos;t get it?{' '}
        {seconds > 0 ? (
          <span className="text-zinc-400">Resend in {seconds}s</span>
        ) : (
          <button type="button" onClick={resend} disabled={resending} className={authLink}>
            {resending ? 'Sending…' : 'Resend code'}
          </button>
        )}
      </p>

      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="mt-4 flex w-full items-center justify-center gap-1.5 text-[13px] text-zinc-500 transition-colors hover:text-primary-400"
        >
          <ArrowLeft size={14} /> {backLabel}
        </button>
      )}

      <p className="mt-5 text-center text-[11px] leading-relaxed text-zinc-600">
        Check your spam folder if it hasn&apos;t arrived within a minute.
      </p>
    </motion.div>
  )
}
