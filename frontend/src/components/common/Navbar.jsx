import { useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'
import Logo from '../ui/Logo'
import UserMenu from './UserMenu'

const pageTitles = {
  '/dashboard':      { title: 'Dashboard',      sub: 'Your AI workspace overview' },
  '/chat':           { title: 'RAG Chatbot',    sub: 'Ask anything about your documents' },
  '/documents':      { title: 'Documents',      sub: 'Manage your knowledge base' },
  '/analytics':      { title: 'Analytics',      sub: 'Usage insights' },
  '/settings':       { title: 'Settings',       sub: 'How your documents are read and answered' },
  '/profile':        { title: 'Profile',        sub: 'Manage your account' },
  '/admin':          { title: 'Admin Panel',    sub: 'System management' },
}

export default function Navbar({ onOpenMenu }) {
  const location = useLocation()

  const page =
    Object.entries(pageTitles).find(
      ([path]) => location.pathname === path || location.pathname.startsWith(path + '/'),
    )?.[1] || { title: 'RAG Chatbot', sub: '' }

  return (
    <header className="z-30 flex h-[60px] shrink-0 items-center gap-3 border-b border-white/[0.06] bg-ink-950/70 px-3 backdrop-blur-xl sm:px-6">
      <button
        onClick={onOpenMenu}
        aria-label="Open menu"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-zinc-400 transition-colors hover:bg-primary-500/10 hover:text-primary-300 lg:hidden"
      >
        <Menu size={19} />
      </button>

      {/* The rail is off-canvas on mobile, so the brand mark lives here instead. */}
      <Logo size={30} id="nav" className="lg:hidden" />

      <div className="min-w-0 flex-1">
        <h1 className="truncate font-display text-sm font-semibold leading-none text-white">{page.title}</h1>
        {page.sub && <p className="mt-1 hidden truncate text-xs text-zinc-500 sm:block">{page.sub}</p>}
      </div>

      {/* Full chip where there's room; avatar-only on phones. */}
      <div className="hidden shrink-0 sm:block sm:w-[172px]">
        <UserMenu align="down" />
      </div>
      <div className="shrink-0 sm:hidden">
        <UserMenu align="down" collapsed />
      </div>
    </header>
  )
}
