import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils'

const sizes = { sm: 'max-w-md', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' }

/* Modals can stack (a source card opens its detail on top of the sources list),
   and body scroll is a single global. Count the open ones so closing the top
   modal doesn't release the lock the one underneath still needs. */
let openCount = 0

function lockBodyScroll() {
  openCount += 1
  document.body.style.overflow = 'hidden'
}

function releaseBodyScroll() {
  openCount = Math.max(0, openCount - 1)
  if (openCount === 0) document.body.style.overflow = ''
}

export default function Modal({ open, onClose, title, children, size = 'md' }) {
  useEffect(() => {
    if (!open) return undefined
    lockBodyScroll()
    return releaseBodyScroll
  }, [open])

  // Escape closes the topmost modal.
  useEffect(() => {
    if (!open) return undefined
    const onKey = e => { if (e.key === 'Escape') onClose?.() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/70 backdrop-blur-md"
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={title || undefined}
            initial={{ opacity: 0, scale: 0.95, y: 18 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 10 }}
            transition={{ type: 'spring', stiffness: 300, damping: 26 }}
            className={cn(
              'relative flex max-h-[90dvh] w-full flex-col overflow-hidden rounded-2xl border border-primary-500/15 bg-ink-850/[0.97] shadow-[0_24px_70px_rgba(0,0,0,0.7)] backdrop-blur-2xl',
              sizes[size],
            )}
          >
            {title && (
              <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-3.5 sm:px-6 sm:py-4">
                <h3 className="min-w-0 truncate font-display text-sm font-semibold text-white">{title}</h3>
                <button
                  onClick={onClose}
                  aria-label="Close dialog"
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-primary-500/10 hover:text-primary-300"
                >
                  <X size={16} />
                </button>
              </div>
            )}
            {/* The body scrolls inside the dialog so a long modal can never
                push the page itself out of bounds on a short screen. */}
            <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
