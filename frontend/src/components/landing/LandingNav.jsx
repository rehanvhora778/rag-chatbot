import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Menu, X, ArrowRight } from 'lucide-react'
import AnimatedButton from '../ui/AnimatedButton'
import { Logo, ThemeToggle, useScrollSpy } from './common'
import { cn } from '../../lib/utils'

const LINKS = [
  { id: 'home',       label: 'Home' },
  { id: 'features',   label: 'Features' },
  { id: 'tech-stack', label: 'Tech Stack' },
  { id: 'how-rag',    label: 'How It Works' },
]
const IDS = LINKS.map(l => l.id)

export default function LandingNav() {
  const navigate = useNavigate()
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)
  const active = useScrollSpy(IDS)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <>
      <motion.header
        initial={{ y: -80, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className={cn(
          'fixed inset-x-0 top-0 z-50 transition-all duration-300',
          scrolled
            ? 'border-b border-zinc-200/70 bg-white/75 backdrop-blur-xl dark:border-white/10 dark:bg-ink-950/70'
            : 'border-b border-transparent bg-transparent',
        )}
      >
        <nav className="mx-auto flex h-[68px] w-full max-w-7xl items-center justify-between px-5 sm:px-8">
          <a href="#home" aria-label="Nexus RAG home">
            <Logo />
          </a>

          {/* desktop links */}
          <ul className="hidden items-center gap-1 lg:flex">
            {LINKS.map(l => (
              <li key={l.id} className="relative">
                <a
                  href={`#${l.id}`}
                  className={cn(
                    'relative flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                    active === l.id ? 'lp-h' : 'lp-sub hover:text-zinc-900 dark:hover:text-white',
                  )}
                >
                  {l.label}
                  {l.soon && (
                    <span className="rounded-full bg-primary-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-primary-600 dark:text-primary-300">
                      Soon
                    </span>
                  )}
                  {active === l.id && (
                    <motion.span
                      layoutId="nav-underline"
                      className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-gradient-to-r from-primary-500 to-accent-500"
                    />
                  )}
                </a>
              </li>
            ))}
          </ul>

          {/* desktop actions */}
          <div className="hidden items-center gap-2 lg:flex">
            <ThemeToggle />
            <button
              onClick={() => navigate('/login')}
              className="rounded-xl px-3.5 py-2 text-sm font-semibold lp-sub transition-colors hover:text-zinc-900 dark:hover:text-white"
            >
              Sign In
            </button>
            <AnimatedButton size="sm" onClick={() => navigate('/register')}>
              Sign Up <ArrowRight size={15} />
            </AnimatedButton>
          </div>

          {/* mobile actions */}
          <div className="flex items-center gap-2 lg:hidden">
            <ThemeToggle />
            <button
              onClick={() => setOpen(o => !o)}
              aria-label="Toggle menu"
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-zinc-200 bg-white/70 lp-h dark:border-white/10 dark:bg-white/5"
            >
              {open ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </nav>
      </motion.header>

      {/* mobile drawer */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 lg:hidden"
          >
            <div className="absolute inset-0 bg-zinc-900/30 backdrop-blur-sm dark:bg-black/60" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', stiffness: 320, damping: 32 }}
              className="absolute right-0 top-0 h-full w-72 border-l border-zinc-200 bg-white p-6 dark:border-white/10 dark:bg-ink-900"
            >
              <div className="mb-8 mt-2 flex items-center justify-between">
                <Logo />
              </div>
              <ul className="space-y-1">
                {LINKS.map(l => (
                  <li key={l.id}>
                    <a
                      href={`#${l.id}`}
                      onClick={() => setOpen(false)}
                      className={cn(
                        'flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors',
                        active === l.id ? 'bg-primary-500/10 text-primary-600 dark:text-primary-300' : 'lp-sub hover:text-zinc-900 dark:hover:text-white',
                      )}
                    >
                      {l.label}
                      {l.soon && <span className="rounded-full bg-primary-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase text-primary-600 dark:text-primary-300">Soon</span>}
                    </a>
                  </li>
                ))}
              </ul>
              <div className="mt-6 space-y-2 border-t border-zinc-200 pt-6 dark:border-white/10">
                <AnimatedButton variant="secondary" className="w-full border-zinc-200 bg-white/80 text-zinc-700 hover:bg-white hover:text-zinc-900 dark:border-white/10 dark:bg-white/5 dark:text-zinc-200 dark:hover:bg-white/10" onClick={() => { setOpen(false); navigate('/login') }}>
                  Sign In
                </AnimatedButton>
                <AnimatedButton className="w-full" onClick={() => { setOpen(false); navigate('/register') }}>
                  Sign Up <ArrowRight size={15} />
                </AnimatedButton>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
