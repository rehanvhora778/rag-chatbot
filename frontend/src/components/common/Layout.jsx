import { useState, useCallback, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import Sidebar from './Sidebar'
import Navbar from './Navbar'

/* Chat manages its own scrolling and fills the viewport edge-to-edge; every
   other page is a normal padded, scrolling document. */
const isChatRoute = pathname => pathname === '/chat' || pathname.startsWith('/chat/')

export default function Layout() {
  const location = useLocation()
  const [glow, setGlow] = useState({ x: -1000, y: -1000 })
  const [mobileOpen, setMobileOpen] = useState(false)

  const onMove = useCallback(e => setGlow({ x: e.clientX, y: e.clientY }), [])
  const closeMobile = useCallback(() => setMobileOpen(false), [])

  // A route change should never leave the drawer hanging open behind the page.
  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  // Lock body scroll while the drawer is open.
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [mobileOpen])

  const chat = isChatRoute(location.pathname)

  return (
    // Gold-rimmed panels float on the page rather than butting edge to edge,
    // so every column reads as its own lit surface.
    <div className="flex h-[100dvh] gap-3 overflow-hidden p-0 lg:p-3">
      <Sidebar mobileOpen={mobileOpen} onCloseMobile={closeMobile} />

      <div className={`relative flex min-w-0 flex-1 flex-col overflow-hidden ${chat ? '' : 'panel-gold'}`}>
        {/* Chat is a full-bleed three-column workspace with its own header, so
            the global top bar would only steal vertical space there. */}
        {!chat && <Navbar onOpenMenu={() => setMobileOpen(true)} />}

        <main
          onMouseMove={onMove}
          className={
            chat
              ? 'relative min-h-0 flex-1 overflow-hidden'
              : 'relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-6'
          }
        >
          {/* Cursor-tracking warm light. Hidden on touch, where there is no
              cursor to track and the extra paint is wasted. */}
          <div
            className="pointer-events-none fixed inset-0 z-0 hidden lg:block"
            style={{
              background: `radial-gradient(620px circle at ${glow.x}px ${glow.y}px, rgba(212,175,55,0.055), transparent 62%)`,
            }}
          />

          <div className="relative z-10 h-full">
            <AnimatePresence mode="wait">
              <motion.div
                key={chat ? '/chat' : location.pathname}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
                className="h-full"
              >
                {/* Chat hides the global navbar, so it needs its own way to
                    open the mobile drawer. */}
                <Outlet context={{ openMenu: () => setMobileOpen(true) }} />
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
      </div>
    </div>
  )
}
