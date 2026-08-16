import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft } from 'lucide-react'
import Brand from '../brand/Brand'
import { PROJECT } from './portfolio'

/**
 * Shared shell for the public legal pages (Terms, Privacy).
 * `sections` is an array of { heading, body?: string[], list?: string[] }.
 */
export default function LegalLayout({ title, updated, intro, sections = [] }) {
  return (
    <div className="min-h-[100dvh] bg-ink-950 text-zinc-300">
      <header className="sticky top-0 z-40 border-b border-white/[0.07] bg-ink-950/80 backdrop-blur-xl">
        <div className="mx-auto flex h-[72px] max-w-3xl items-center justify-between px-5 sm:px-8">
          <Link to="/" aria-label="RAG Chatbot home"><Brand size={30} nameSize="sm" id="legal-brand" /></Link>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-sm font-semibold text-zinc-300 transition-colors hover:border-primary-500/35 hover:text-white"
          >
            <ArrowLeft size={15} /> Home
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-14 sm:px-8">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
          <h1 className="font-display text-3xl font-bold tracking-tight text-white sm:text-4xl">{title}</h1>
          {updated && <p className="mt-2 text-sm text-zinc-500">Last updated: {updated}</p>}
          {intro && <p className="mt-6 text-base leading-relaxed text-zinc-400">{intro}</p>}

          <div className="mt-10 space-y-8">
            {sections.map((s, i) => (
              <section key={i}>
                <h2 className="font-display text-lg font-semibold text-white">{s.heading}</h2>
                {s.body?.map((p, j) => (
                  <p key={j} className="mt-2 text-sm leading-relaxed text-zinc-400">{p}</p>
                ))}
                {s.list && (
                  <ul className="mt-3 space-y-1.5">
                    {s.list.map((li, j) => (
                      <li key={j} className="flex gap-2.5 text-sm leading-relaxed text-zinc-400">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary-400" />
                        {li}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
          </div>

          <div className="mt-12 rounded-2xl border border-white/10 bg-white/[0.03] p-5 text-sm text-zinc-400">
            This project is an academic demonstration of Retrieval-Augmented Generation. Questions? Email{' '}
            <a href={`mailto:${PROJECT.email}`} className="font-semibold text-primary-400 hover:underline">{PROJECT.email}</a>.
          </div>
        </motion.div>
      </main>

      <footer className="border-t border-white/[0.07] px-5 py-8 sm:px-8">
        <div className="mx-auto flex max-w-3xl flex-col items-center justify-between gap-3 text-xs text-zinc-600 sm:flex-row">
          <p>© {new Date().getFullYear()} RAG Chatbot — {PROJECT.type}. All rights reserved.</p>
          <div className="flex gap-4">
            <Link to="/privacy" className="transition-colors hover:text-primary-400">Privacy</Link>
            <Link to="/terms" className="transition-colors hover:text-primary-400">Terms</Link>
            <Link to="/" className="transition-colors hover:text-primary-400">Home</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
