import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRight, Menu, X } from 'lucide-react'
import Brand from '../brand/Brand'
import { cn } from '../../lib/utils'

export const NAV_LINKS = [
  { id: 'home',        label: 'Home' },
  { id: 'features',    label: 'Features' },
  { id: 'how-it-works', label: 'How It Works' },
  { id: 'about',       label: 'About' },
  { id: 'docs',        label: 'Docs' },
]

/** Tracks which section is under the navbar so its link can light up. */
function useActiveSection() {
  const [active, setActive] = useState(NAV_LINKS[0].id)
  useEffect(() => {
    const onScroll = () => {
      const line = window.scrollY + 140
      let current = NAV_LINKS[0].id
      let best = -Infinity
      for (const { id } of NAV_LINKS) {
        const el = document.getElementById(id)
        if (el && el.offsetTop <= line && el.offsetTop > best) {
          best = el.offsetTop
          current = id
        }
      }
      setActive(current)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [])
  return active
}

export default function HomeNav() {
  const navigate = useNavigate()
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)
  const active = useActiveSection()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <>
      <motion.header
        initial={{ y: -70, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className={cn(
          'fixed inset-x-0 top-0 z-50 transition-all duration-300',
          scrolled ? 'border-b border-white/[0.07] bg-ink-950/80 backdrop-blur-xl' : 'border-b border-transparent',
        )}
      >
        <nav className="mx-auto flex h-[76px] w-full max-w-7xl items-center justify-between px-5 sm:px-8">
          <a href="#home" aria-label="RAG Chatbot home">
            <Brand size={34} />
          </a>

          <ul className="hidden items-center gap-1 lg:flex">
            {NAV_LINKS.map(l => (
              <li key={l.id}>
                <a
                  href={`#${l.id}`}
                  className={cn(
                    'relative block px-3.5 py-2 text-sm font-medium transition-colors',
                    active === l.id ? 'text-primary-400' : 'text-zinc-400 hover:text-white',
                  )}
                >
                  {l.label}
                  {active === l.id && (
                    <motion.span
                      layoutId="home-nav-underline"
                      className="absolute inset-x-3 -bottom-0.5 h-0.5 rounded-full bg-primary-400"
                    />
                  )}
                </a>
              </li>
            ))}
          </ul>

          <div className="hidden items-center gap-3 lg:flex">
            <Link
              to="/login"
              className="rounded-xl border border-white/12 px-5 py-2.5 text-sm font-semibold text-zinc-200 transition-all duration-200 hover:border-primary-500/40 hover:text-white"
            >
              Login
            </Link>
            <Link
              to="/register"
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-b from-primary-300 via-primary-400 to-primary-500 px-5 py-2.5 text-sm font-semibold text-ink-950 shadow-[0_6px_22px_rgba(212,175,55,0.3)] transition-shadow duration-200 hover:shadow-[0_8px_30px_rgba(212,175,55,0.45)]"
            >
              Get Started <ArrowRight size={15} />
            </Link>
          </div>

          <button
            onClick={() => setOpen(o => !o)}
            aria-label="Toggle menu"
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-white lg:hidden"
          >
            {open ? <X size={18} /> : <Menu size={18} />}
          </button>
        </nav>
      </motion.header>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 lg:hidden"
          >
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', stiffness: 320, damping: 32 }}
              className="absolute right-0 top-0 h-full w-72 border-l border-white/10 bg-ink-900 p-6"
            >
              <div className="mb-8 mt-1"><Brand size={30} nameSize="sm" /></div>
              <ul className="space-y-1">
                {NAV_LINKS.map(l => (
                  <li key={l.id}>
                    <a
                      href={`#${l.id}`}
                      onClick={() => setOpen(false)}
                      className={cn(
                        'block rounded-xl px-3 py-2.5 text-sm font-medium transition-colors',
                        active === l.id ? 'bg-primary-500/10 text-primary-300' : 'text-zinc-400 hover:text-white',
                      )}
                    >
                      {l.label}
                    </a>
                  </li>
                ))}
              </ul>
              <div className="mt-6 space-y-2 border-t border-white/10 pt-6">
                <button
                  onClick={() => { setOpen(false); navigate('/login') }}
                  className="w-full rounded-xl border border-white/12 py-2.5 text-sm font-semibold text-zinc-200"
                >
                  Login
                </button>
                <button
                  onClick={() => { setOpen(false); navigate('/register') }}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-b from-primary-300 to-primary-500 py-2.5 text-sm font-semibold text-ink-950"
                >
                  Get Started <ArrowRight size={15} />
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
