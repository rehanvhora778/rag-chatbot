import { forwardRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Eye, EyeOff } from 'lucide-react'
import { cn } from '../../lib/utils'

/* ── Labelled text input ──────────────────────────────────────────────── */
export const Field = forwardRef(function Field(
  { label, error, hint, rightSlot, className, ...props },
  ref,
) {
  return (
    <div className="w-full">
      {label && <label className="mb-1.5 block text-[13px] font-medium text-zinc-300">{label}</label>}
      <div className="relative">
        <input
          ref={ref}
          className={cn(
            'h-11 w-full rounded-xl border border-white/10 bg-white/[0.03] px-3.5 text-sm text-zinc-100',
            'outline-none transition-all duration-200 placeholder:text-zinc-600',
            'hover:border-white/20 focus:border-primary-500/60 focus:ring-2 focus:ring-primary-500/20',
            rightSlot && 'pr-11',
            error && 'border-red-500/70 focus:border-red-500/70 focus:ring-red-500/20',
            className,
          )}
          {...props}
        />
        {rightSlot && <div className="absolute right-3 top-1/2 -translate-y-1/2">{rightSlot}</div>}
      </div>
      {error && <p className="mt-1.5 text-xs font-medium text-red-400">{error}</p>}
      {hint && !error && <div className="mt-1.5">{hint}</div>}
    </div>
  )
})

/* ── Password input with a reveal toggle ──────────────────────────────── */
export function PasswordField({ label = 'Password', ...props }) {
  const [show, setShow] = useState(false)
  return (
    <Field
      {...props}
      label={label}
      type={show ? 'text' : 'password'}
      rightSlot={
        <button
          type="button"
          onClick={() => setShow(v => !v)}
          aria-label={show ? 'Hide password' : 'Show password'}
          className="text-zinc-500 transition-colors hover:text-primary-400"
        >
          {show ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      }
    />
  )
}

/* ── Checkbox ─────────────────────────────────────────────────────────── */
export function Check({ checked, onChange, children, error, className }) {
  return (
    <label className={cn('flex cursor-pointer select-none items-start gap-2.5 text-[13px] text-zinc-400', className)}>
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        className={cn(
          'mt-0.5 h-4 w-4 shrink-0 rounded border-white/25 bg-transparent accent-primary-500',
          error && 'ring-2 ring-red-500/40',
        )}
      />
      <span>{children}</span>
    </label>
  )
}

/* ── Primary submit button ────────────────────────────────────────────── */
export function SubmitButton({ loading, children, loadingLabel = 'Please wait…', className, ...props }) {
  return (
    <motion.button
      type="submit"
      whileHover={{ scale: loading ? 1 : 1.01 }}
      whileTap={{ scale: loading ? 1 : 0.985 }}
      transition={{ type: 'spring', stiffness: 400, damping: 18 }}
      disabled={loading}
      className={cn(
        'relative flex h-11 w-full items-center justify-center gap-2 overflow-hidden rounded-xl',
        'bg-gradient-to-b from-primary-300 via-primary-400 to-primary-500 text-[15px] font-semibold text-ink-950',
        'shadow-[0_6px_24px_rgba(212,175,55,0.28)] transition-shadow duration-200',
        'hover:shadow-[0_8px_34px_rgba(212,175,55,0.42)] disabled:cursor-not-allowed disabled:opacity-70',
        className,
      )}
      {...props}
    >
      {loading ? (
        <>
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-950/30 border-t-ink-950" />
          {loadingLabel}
        </>
      ) : (
        children
      )}
    </motion.button>
  )
}

/* ── Card that every auth form sits in ────────────────────────────────── */
export function AuthCard({ className, children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        'relative w-full rounded-3xl border border-primary-500/15 bg-[#0b0b0d]/90 p-6 backdrop-blur-2xl sm:p-8',
        'shadow-[inset_0_1px_0_rgba(245,197,66,0.07),0_24px_70px_rgba(0,0,0,0.65)]',
        className,
      )}
    >
      {children}
    </motion.div>
  )
}

export const authLink =
  'font-semibold text-primary-400 transition-colors hover:text-primary-300 hover:underline'
