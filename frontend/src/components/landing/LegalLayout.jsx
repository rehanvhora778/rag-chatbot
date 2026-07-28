import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft } from 'lucide-react'
import { Logo, ThemeToggle } from './common'
import { PROJECT } from './portfolio'

/**
 * Shared shell for the public legal pages (Terms, Privacy). Themeable (light/
 * dark), normal scrolling (no scroll-snap). `sections` is an array of
 * { heading, body?: string[], list?: string[] }.
 */
export default function LegalLayout({ title, updated, intro, sections = [] }) {
  return (
    <div className="min-h-[100dvh] bg-[#fbfbfe] text-zinc-700 transition-colors duration-300 dark:bg-ink-950 dark:text-zinc-300">
      {/* top bar */}
      <header className="sticky top-0 z-40 border-b border-zinc-200/70 bg-white/75 backdrop-blur-xl dark:border-white/10 dark:bg-ink-950/70">
        <div className="mx-auto flex h-[68px] max-w-3xl items-center justify-between px-5 sm:px-8">
          <Link to="/" aria-label="Nexus RAG home"><Logo /></Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link
              to="/"
              className="inline-flex items-center gap-1.5 rounded-xl border border-zinc-200 bg-white/70 px-3 py-2 text-sm font-semibold lp-sub transition-colors hover:text-zinc-900 dark:border-white/10 dark:bg-white/5 dark:hover:text-white"
            >
              <ArrowLeft size={15} /> Home
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-14 sm:px-8">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
          <h1 className="font-display text-3xl font-bold tracking-tight lp-h sm:text-4xl">{title}</h1>
          {updated && <p className="mt-2 text-sm lp-sub">Last updated: {updated}</p>}
          {intro && <p className="mt-6 text-base leading-relaxed lp-sub">{intro}</p>}

          <div className="mt-10 space-y-8">
            {sections.map((s, i) => (
              <section key={i}>
                <h2 className="font-display text-lg font-semibold lp-h">{s.heading}</h2>
                {s.body?.map((p, j) => (
                  <p key={j} className="mt-2 text-sm leading-relaxed lp-sub">{p}</p>
                ))}
                {s.list && (
                  <ul className="mt-3 space-y-1.5">
                    {s.list.map((li, j) => (
                      <li key={j} className="flex gap-2.5 text-sm leading-relaxed lp-sub">
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-gradient-to-br from-primary-500 to-accent-600" />
                        {li}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
          </div>

          <div className="mt-12 rounded-2xl border border-zinc-200/80 bg-white/60 p-5 text-sm lp-sub dark:border-white/10 dark:bg-white/[0.03]">
            This project is an academic / portfolio demonstration of Retrieval-Augmented Generation. Questions? Email{' '}
            <a href={`mailto:${PROJECT.email}`} className="font-semibold text-primary-600 hover:underline dark:text-primary-400">{PROJECT.email}</a>.
          </div>
        </motion.div>
      </main>

      <footer className="border-t border-zinc-200/70 px-5 py-8 dark:border-white/10 sm:px-8">
        <div className="mx-auto flex max-w-3xl flex-col items-center justify-between gap-3 text-xs lp-sub sm:flex-row">
          <p>© {new Date().getFullYear()} {PROJECT.name} — {PROJECT.type}. All rights reserved.</p>
          <div className="flex gap-4">
            <Link to="/privacy" className="transition-colors hover:text-primary-600 dark:hover:text-primary-300">Privacy</Link>
            <Link to="/terms" className="transition-colors hover:text-primary-600 dark:hover:text-primary-300">Terms</Link>
            <Link to="/" className="transition-colors hover:text-primary-600 dark:hover:text-primary-300">Home</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
