import { forwardRef } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft, ShieldCheck, Quote, Search, GraduationCap } from 'lucide-react'
import AuroraBackground from '../ui/AuroraBackground'
import ParticleBackground from '../ui/ParticleBackground'
import { Logo, ThemeToggle } from './common'
import { PROJECT, TEAM_NAMES } from './portfolio'
import { cn } from '../../lib/utils'

const PANEL_FEATURES = [
  { icon: Search, text: 'Semantic search across all your documents' },
  { icon: Quote, text: 'Every answer backed by verifiable citations' },
  { icon: ShieldCheck, text: 'Private & secure — never used to train models' },
]

/* ── Split-screen auth shell ──────────────────────────────────── */
export function AuthShell({ heading, subheading, children }) {
  return (
    <div className="relative flex min-h-screen bg-[#fbfbfe] dark:bg-ink-950">
      {/* left brand panel — always dark */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-gradient-to-br from-ink-950 via-[#1a1340] to-ink-900 p-12 lg:flex">
        <AuroraBackground />
        <ParticleBackground count={26} />
        <Link to="/" className="relative z-10 w-fit">
          <Logo tone="light" />
        </Link>

        <div className="relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs font-semibold tracking-wide text-zinc-200 backdrop-blur-xl"
          >
            <GraduationCap size={14} className="text-primary-300" />
            Project · Retrieval-Augmented Generation
          </motion.div>
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className="max-w-md font-display text-4xl font-bold leading-tight text-white"
          >
            Chat with your documents.{' '}
            <span className="bg-gradient-to-r from-primary-300 to-accent-300 bg-clip-text text-transparent">
              Get cited answers.
            </span>
          </motion.h2>
          <p className="mt-4 max-w-md text-base leading-relaxed text-zinc-400">
            Upload anything, ask in plain language, and let Retrieval-Augmented Generation do the reading for you.
          </p>

          <ul className="mt-8 space-y-4">
            {PANEL_FEATURES.map((f, i) => (
              <motion.li
                key={f.text}
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2 + i * 0.1 }}
                className="flex items-center gap-3 text-sm text-zinc-300"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-primary-300">
                  <f.icon size={16} />
                </span>
                {f.text}
              </motion.li>
            ))}
          </ul>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="relative z-10 rounded-2xl border border-white/10 bg-white/[0.04] p-4 backdrop-blur-xl"
        >
          <p className="text-[11px] font-semibold uppercase tracking-wider text-primary-300">Project</p>
          <p className="mt-1.5 text-sm leading-relaxed text-zinc-200">
            A Retrieval-Augmented Generation chatbot, designed &amp; built by{' '}
            <span className="font-semibold text-white">{TEAM_NAMES}</span>.
          </p>
          <p className="mt-1 text-xs text-zinc-400">{PROJECT.college}</p>
        </motion.div>
      </div>

      {/* right form side — themeable */}
      <div className="relative flex w-full flex-col lg:w-1/2">
        <div className="flex items-center justify-between p-5 sm:p-6">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-sm font-medium lp-sub transition-colors hover:text-primary-600 dark:hover:text-primary-300"
          >
            <ArrowLeft size={15} /> Back to home
          </Link>
          <ThemeToggle />
        </div>

        <div className="flex flex-1 items-center justify-center px-5 pb-12 sm:px-8">
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="w-full max-w-md"
          >
            {/* mobile logo */}
            <Link to="/" className="mb-8 flex justify-center lg:hidden">
              <Logo />
            </Link>
            <h1 className="font-display text-2xl font-bold tracking-tight lp-h sm:text-3xl">{heading}</h1>
            {subheading && <p className="mt-2 text-sm lp-sub">{subheading}</p>}
            <div className="mt-7">{children}</div>
          </motion.div>
        </div>
      </div>
    </div>
  )
}

/* ── Themeable input ──────────────────────────────────────────── */
export const Field = forwardRef(function Field(
  { label, icon: Icon, error, rightSlot, hint, className, ...props },
  ref,
) {
  return (
    <div className="w-full">
      {label && (
        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider lp-sub">{label}</label>
      )}
      <div className="relative">
        {Icon && (
          <Icon size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-400 dark:text-zinc-500" />
        )}
        <input
          ref={ref}
          className={cn(
            'w-full rounded-xl border bg-white/80 px-3.5 py-2.5 text-sm font-medium text-zinc-900 outline-none transition-all duration-200 placeholder:text-zinc-400',
            'border-zinc-200 hover:border-zinc-300 focus:border-primary-500/60 focus:ring-2 focus:ring-primary-500/25',
            'dark:border-white/10 dark:bg-white/[0.04] dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:hover:border-white/20',
            Icon && 'pl-10',
            rightSlot && 'pr-11',
            error && 'border-red-500/70 focus:border-red-500/70 focus:ring-red-500/20',
            className,
          )}
          {...props}
        />
        {rightSlot && <div className="absolute right-3 top-1/2 -translate-y-1/2">{rightSlot}</div>}
      </div>
      {error && <p className="mt-1.5 text-xs font-medium text-red-500">{error}</p>}
      {hint && !error && <div className="mt-1.5">{hint}</div>}
    </div>
  )
})

/* ── Divider ──────────────────────────────────────────────────── */
export function Divider({ children }) {
  return (
    <div className="my-5 flex items-center gap-3">
      <span className="h-px flex-1 bg-zinc-200 dark:bg-white/10" />
      <span className="text-xs font-medium lp-sub">{children}</span>
      <span className="h-px flex-1 bg-zinc-200 dark:bg-white/10" />
    </div>
  )
}
