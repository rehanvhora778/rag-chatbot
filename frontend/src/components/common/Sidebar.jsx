import { useState, useEffect, useCallback } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  FileText, MessageSquare, BarChart2,
  ShieldCheck, Plus, ChevronRight, Clock,
  PanelLeftClose, PanelLeftOpen, X,
} from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { chatAPI } from '../../api/chat'
import { cn } from '../../lib/utils'
import Logo from '../ui/Logo'
import UserMenu from './UserMenu'

/* Main navigation, in the agreed order. Dashboard is deliberately not here —
   it lives in the account menu so this list stays the primary areas. */
const navItems = [
  { to: '/chat',      label: 'Chats',     icon: MessageSquare },
  { to: '/documents', label: 'Documents', icon: FileText },
  { to: '/analytics', label: 'Analytics', icon: BarChart2 },
]

const adminItems = [{ to: '/admin', label: 'Admin Panel', icon: ShieldCheck }]

/* Relative timestamps, so Recent Chats reads like an activity feed. */
function timeAgo(iso) {
  if (!iso) return ''
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (Number.isNaN(secs)) return ''
  if (secs < 60)     return 'just now'
  if (secs < 3600)   return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400)  return `${Math.floor(secs / 3600)}h ago`
  if (secs < 172800) return 'Yesterday'
  if (secs < 604800) return `${Math.floor(secs / 86400)}d ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function NavItem({ to, label, icon: Icon, active, collapsed, onNavigate }) {
  return (
    <Link
      to={to}
      onClick={onNavigate}
      title={collapsed ? label : undefined}
      className={cn(
        'row-gold group relative flex items-center gap-3 px-3.5 py-2.5 text-sm font-medium',
        active ? 'row-gold-active text-primary-100' : 'text-zinc-300 hover:text-primary-100',
        collapsed && 'justify-center px-0',
      )}
    >
      <Icon
        size={17}
        className={cn(
          'shrink-0 transition-colors',
          active ? 'text-primary-400' : 'text-primary-500/70 group-hover:text-primary-400',
        )}
      />
      {!collapsed && <span className="truncate">{label}</span>}
    </Link>
  )
}

function RecentChat({ session, active, onNavigate }) {
  return (
    <Link
      to={`/chat/${session.id}`}
      onClick={onNavigate}
      className={cn(
        'row-gold group flex items-center gap-2.5 px-3 py-2.5',
        active && 'row-gold-active',
      )}
    >
      <span className="min-w-0 flex-1">
        <span className={cn('block truncate text-[12.5px] font-medium leading-tight', active ? 'text-primary-100' : 'text-zinc-200')}>
          {session.title}
        </span>
        <span className="mt-1 block truncate text-[10px] text-zinc-600">
          {timeAgo(session.last_message_at || session.updated_at)}
        </span>
      </span>
      {active && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary-400 shadow-[0_0_8px_rgba(245,197,66,0.9)]" />}
      <ChevronRight size={13} className="shrink-0 text-primary-500/50 transition-all group-hover:translate-x-0.5 group-hover:text-primary-400" />
    </Link>
  )
}

/**
 * Sidebar — one component, two presentations:
 *   ≥ lg : a fixed rail that collapses to icons (persisted to localStorage)
 *   < lg : an off-canvas drawer driven by `mobileOpen` from Layout
 */
export default function Sidebar({ mobileOpen = false, onCloseMobile }) {
  const { user } = useAuth()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('sidebar_collapsed') === '1')
  const [sessions, setSessions] = useState([])

  const isActive = to => pathname === to || pathname.startsWith(to + '/')

  const loadSessions = useCallback(() => {
    chatAPI.listSessions({ page_size: 5 })
      .then(res => setSessions(res.data.data || []))
      .catch(() => { /* the rail is ambient — never surface an error here */ })
  }, [])

  useEffect(() => { loadSessions() }, [loadSessions])

  // ChatPage broadcasts this after create / rename / delete so the rail stays
  // in step without lifting chat state into a global store.
  useEffect(() => {
    window.addEventListener('chat-sessions-changed', loadSessions)
    return () => window.removeEventListener('chat-sessions-changed', loadSessions)
  }, [loadSessions])

  const toggle = () => {
    setCollapsed(c => {
      localStorage.setItem('sidebar_collapsed', c ? '0' : '1')
      return !c
    })
  }

  const startNewChat = () => {
    onCloseMobile?.()
    navigate('/chat?new=1')   // ChatPage reads ?new=1 and opens the document picker
  }

  // Collapsing only applies to the desktop rail; the drawer is always full width.
  const isCollapsed = collapsed && !mobileOpen

  const body = (
    <>
      {/* ── Branding ── */}
      <div className={cn('flex shrink-0 items-center gap-3 px-4 pb-3 pt-4', isCollapsed && 'justify-center px-0')}>
        <Link to="/chat" onClick={onCloseMobile} className="flex min-w-0 items-center gap-3">
          <Logo size={42} id="sidebar" />
          {!isCollapsed && (
            <span className="min-w-0 overflow-hidden">
              <span className="block truncate font-display text-[16px] font-bold leading-tight text-white">RAG Chatbot</span>
              <span className="mt-0.5 block truncate text-[10.5px] font-medium text-zinc-500">
                AI-Powered Assistant
              </span>
            </span>
          )}
        </Link>
        {mobileOpen && (
          <button
            onClick={onCloseMobile}
            aria-label="Close menu"
            className="ml-auto flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-zinc-400 transition-colors hover:bg-white/5 hover:text-white lg:hidden"
          >
            <X size={18} />
          </button>
        )}
      </div>

      {/* ── New Chat ── */}
      <div className={cn('shrink-0 px-3 pb-3', isCollapsed && 'px-2')}>
        <button
          onClick={startNewChat}
          title={isCollapsed ? 'New Chat' : undefined}
          className={cn(
            'group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-2xl',
            'bg-gradient-to-b from-primary-300 via-primary-400 to-primary-600 font-bold text-ink-950',
            'shadow-[0_3px_20px_rgba(212,175,55,0.35)] transition-all duration-200',
            'hover:shadow-[0_3px_30px_rgba(212,175,55,0.55)] active:scale-[0.985]',
            isCollapsed ? 'h-11 w-11 px-0' : 'px-4 py-3 text-[14px]',
          )}
        >
          <span className="pointer-events-none absolute inset-y-0 -left-full w-1/2 skew-x-[-18deg] bg-white/40 group-hover:animate-shine" />
          <Plus size={isCollapsed ? 19 : 17} strokeWidth={3} />
          {!isCollapsed && 'New Chat'}
        </button>
      </div>

      {/* ── Scrolling region: nav + recents ── */}
      <nav className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 pb-3">
        {!isCollapsed && (
          <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-zinc-600">Workspace</p>
        )}
        <div className="space-y-1.5">
          {navItems.map(itemProps => (
            <NavItem
              key={itemProps.to}
              {...itemProps}
              active={isActive(itemProps.to)}
              collapsed={isCollapsed}
              onNavigate={onCloseMobile}
            />
          ))}

          {user?.is_staff && (
            <>
              <div className="rule-gold my-2.5" />
              {adminItems.map(itemProps => (
                <NavItem
                  key={itemProps.to}
                  {...itemProps}
                  active={isActive(itemProps.to)}
                  collapsed={isCollapsed}
                  onNavigate={onCloseMobile}
                />
              ))}
            </>
          )}
        </div>

        {!isCollapsed && (
          <>
            <div className="mb-2 mt-5 flex items-center justify-between px-1">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-zinc-600">Recent Chats</p>
              <Clock size={11} className="text-zinc-600" />
            </div>

            {sessions.length === 0 ? (
              <p className="px-1 py-2 text-[11px] leading-relaxed text-zinc-600">
                No conversations yet. Start one to see it here.
              </p>
            ) : (
              <div className="space-y-1.5">
                {sessions.map(s => (
                  <RecentChat
                    key={s.id}
                    session={s}
                    active={pathname === `/chat/${s.id}`}
                    onNavigate={onCloseMobile}
                  />
                ))}
              </div>
            )}

            <Link
              to="/chat"
              onClick={onCloseMobile}
              className="mt-2 flex items-center gap-1 px-1 py-1.5 text-[11.5px] font-semibold text-primary-400 transition-colors hover:text-primary-300"
            >
              View all chats <ChevronRight size={12} />
            </Link>
          </>
        )}
      </nav>

      {/* ── User ── */}
      <div className="shrink-0 border-t border-primary-500/20 p-3">
        <UserMenu collapsed={isCollapsed} onNavigate={onCloseMobile} />
      </div>
    </>
  )

  return (
    <>
      {/* Desktop rail */}
      <motion.aside
        animate={{ width: collapsed ? 84 : 276 }}
        initial={false}
        transition={{ type: 'spring', stiffness: 300, damping: 32 }}
        className="panel-gold relative z-20 hidden shrink-0 flex-col lg:flex"
      >
        {body}
        <button
          onClick={toggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={collapsed ? 'Expand' : 'Collapse'}
          className="absolute -right-3 top-[86px] z-30 flex h-6 w-6 items-center justify-center rounded-full border border-primary-500/25 bg-ink-800 text-primary-400/80 shadow-md transition-colors hover:bg-ink-700 hover:text-primary-300"
        >
          {collapsed ? <PanelLeftOpen size={13} /> : <PanelLeftClose size={13} />}
        </button>
      </motion.aside>

      {/* Mobile drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={onCloseMobile}
              className="absolute inset-0 bg-black/75 backdrop-blur-sm"
            />
            <motion.aside
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'spring', stiffness: 380, damping: 38 }}
              className="absolute inset-y-0 left-0 flex w-[min(86vw,300px)] flex-col border-r border-primary-500/15 bg-ink-900 shadow-[8px_0_40px_rgba(0,0,0,0.6)]"
            >
              {body}
            </motion.aside>
          </div>
        )}
      </AnimatePresence>
    </>
  )
}
