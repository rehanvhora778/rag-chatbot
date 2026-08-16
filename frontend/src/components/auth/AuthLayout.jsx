import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft } from 'lucide-react'
import Brand from '../brand/Brand'
import ValleyArt from './ValleyArt'
import { cn } from '../../lib/utils'

/**
 * Full-height brand panel down the left edge of the split auth screens. The
 * valley art is the panel's background, with the logo and headline over it.
 */
export function AuthAside({ title, subtitle }) {
  return (
    <aside className="relative hidden overflow-hidden border-r border-primary-500/[0.12] bg-[#08080a] lg:block">
      <ValleyArt />
      <motion.div
        initial={{ opacity: 0, x: -16 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        className="relative z-10 flex h-full flex-col p-10 xl:p-12"
      >
        <Link to="/" className="w-fit">
          <Brand size={32} nameSize="sm" />
        </Link>

        <div className="mt-14 xl:mt-16">
          <h2 className="font-display text-[2.1rem] font-bold leading-tight tracking-tight text-white xl:text-[2.5rem]">
            {title}
          </h2>
          <p className="mt-3 max-w-[16rem] text-sm leading-relaxed text-zinc-400">{subtitle}</p>
        </div>
      </motion.div>
    </aside>
  )
}

/**
 * Every auth screen fills the viewport.
 *
 * Pass `aside` for the two-column split (login, register); leave it out for a
 * centred card on the ambient background (admin login).
 */
export default function AuthLayout({ aside, children, width = 'md' }) {
  const formColumn = (
    <div className="relative flex min-h-[100dvh] flex-col px-5 py-5 sm:px-8 lg:px-12">
      {/* ambient gold lighting */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            'radial-gradient(ellipse 75% 45% at 50% -8%, rgba(212,175,55,0.13), transparent 64%),' +
            'radial-gradient(ellipse 50% 40% at 100% 30%, rgba(176,126,40,0.08), transparent 60%),' +
            'radial-gradient(ellipse 60% 45% at 0% 95%, rgba(212,175,55,0.06), transparent 62%)',
        }}
      />

      <Link
        to="/"
        className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-zinc-500 transition-colors hover:text-primary-400"
      >
        <ArrowLeft size={15} /> Back to home
      </Link>

      <div className="flex flex-1 items-center justify-center py-4">
        <div className={cn('w-full', aside ? 'max-w-[28rem]' : width === 'lg' ? 'max-w-lg' : 'max-w-md')}>
          {/* the aside carries the brand on desktop; small screens get it here */}
          {aside && (
            <Link to="/" className="mb-7 flex justify-center lg:hidden">
              <Brand size={30} nameSize="sm" />
            </Link>
          )}
          {children}
        </div>
      </div>
    </div>
  )

  if (!aside) return <div className="bg-ink-950">{formColumn}</div>

  return (
    <div className="grid min-h-[100dvh] bg-ink-950 lg:grid-cols-[minmax(0,0.72fr)_minmax(0,1.28fr)]">
      {aside}
      {formColumn}
    </div>
  )
}
