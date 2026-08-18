import { useState, useRef, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { User, LogOut, ChevronsUpDown, ShieldCheck, LayoutDashboard } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../../contexts/AuthContext'
import { cn } from '../../lib/utils'

/**
 * Account chip + popover menu.
 *
 * The chip's secondary line shows the account's real role (Administrator /
 * Member) — this project has no billing or subscription data, so there is no
 * plan to display.
 */
export default function UserMenu({ collapsed = false, onNavigate, align = 'up' }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDown = e => { if (!ref.current?.contains(e.target)) setOpen(false) }
    const onEsc  = e => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onEsc)
    }
  }, [open])

  const handleLogout = async () => {
    setLoggingOut(true)
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch {
      toast.error('Could not sign out. Please try again.')
    } finally {
      setLoggingOut(false)
      setOpen(false)
    }
  }

  const initial = user?.username?.[0]?.toUpperCase() || '?'
  const role = user?.is_staff ? 'Administrator' : 'Member'

  const go = to => { setOpen(false); onNavigate?.(); navigate(to) }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={collapsed ? user?.username : undefined}
        className={cn(
          'flex w-full items-center gap-3 rounded-xl border border-transparent p-2 transition-colors',
          'hover:border-primary-500/20 hover:bg-primary-500/[0.06]',
          open && 'border-primary-500/25 bg-primary-500/[0.08]',
          collapsed && 'justify-center p-1.5',
        )}
      >
        <span className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary-400 to-accent-600 text-[13px] font-bold text-ink-950 shadow-glow-sm">
          {initial}
        </span>
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1 text-left">
              <span className="block truncate text-[13px] font-semibold text-zinc-100">
                {user?.full_name || user?.username}
              </span>
              <span className="mt-0.5 flex items-center gap-1 text-[10px] text-zinc-500">
                {user?.is_staff && <ShieldCheck size={10} className="text-primary-500" />}
                {role}
              </span>
            </span>
            <ChevronsUpDown size={14} className="shrink-0 text-zinc-600" />
          </>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: align === 'up' ? 8 : -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: align === 'up' ? 6 : -6, scale: 0.98 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            className={cn(
              // The opacity modifier must be a bracketed value: Tailwind's default
              // scale steps by 5, so a bare `/97` compiles to nothing at all and
              // leaves the menu transparent over the page behind it.
              'absolute z-50 w-56 overflow-hidden rounded-xl border border-primary-500/30 bg-ink-850/[0.97] p-1.5 shadow-[0_16px_50px_rgba(0,0,0,0.7)] backdrop-blur-2xl',
              align === 'up' ? 'bottom-full mb-2' : 'top-full mt-2',
              // Anchored to the edge the trigger sits nearest so it can't run
              // off-screen. Only the expanded sidebar chip is wide enough to
              // stretch the menu to its own width.
              align === 'down' || collapsed
                ? (align === 'down' ? 'right-0' : 'left-0')
                : 'inset-x-0',
            )}
          >
            <div className="border-b border-primary-500/20 px-3 pb-2.5 pt-2">
              <p className="truncate text-[13px] font-semibold text-white">{user?.full_name || user?.username}</p>
              <p className="truncate text-[11px] text-zinc-500">{user?.email || role}</p>
            </div>

            <div className="pt-1.5">
              <button role="menuitem" onClick={() => go('/dashboard')} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-zinc-300 transition-colors hover:bg-primary-500/10 hover:text-primary-200">
                <LayoutDashboard size={14} className="text-zinc-500" /> Dashboard
              </button>
              <button role="menuitem" onClick={() => go('/profile')} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-zinc-300 transition-colors hover:bg-primary-500/10 hover:text-primary-200">
                <User size={14} className="text-zinc-500" /> Profile
              </button>
              {user?.is_staff && (
                <button role="menuitem" onClick={() => go('/admin')} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-zinc-300 transition-colors hover:bg-primary-500/10 hover:text-primary-200">
                  <ShieldCheck size={14} className="text-zinc-500" /> Admin Panel
                </button>
              )}
            </div>

            <div className="mt-1.5 border-t border-primary-500/20 pt-1.5">
              <button
                role="menuitem"
                onClick={handleLogout}
                disabled={loggingOut}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-red-400 transition-colors hover:bg-red-500/10 disabled:opacity-50"
              >
                <LogOut size={14} /> {loggingOut ? 'Signing out…' : 'Sign out'}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
