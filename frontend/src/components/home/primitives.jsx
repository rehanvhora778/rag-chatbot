import { motion } from 'framer-motion'
import { cn } from '../../lib/utils'

/** Standard page section: full-width band, centred content, nav-safe anchor. */
export function Section({ id, className, children }) {
  return (
    <section id={id} className={cn('relative scroll-mt-24 px-5 py-20 sm:px-8 sm:py-24', className)}>
      <div className="mx-auto w-full max-w-7xl">{children}</div>
    </section>
  )
}

/** Fades + lifts its child the first time it scrolls into view. */
export function Reveal({ children, delay = 0, y = 18, className }) {
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/** Small gold capsule used above section headings. */
export function Eyebrow({ children, className }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full border border-primary-500/30 bg-primary-500/[0.08]',
        'px-3.5 py-1.5 text-xs font-semibold tracking-wide text-primary-300',
        className,
      )}
    >
      {children}
    </span>
  )
}

export function SectionHeading({ eyebrow, title, subtitle, className }) {
  return (
    <div className={cn('mx-auto max-w-2xl text-center', className)}>
      {eyebrow && <Reveal><Eyebrow>{eyebrow}</Eyebrow></Reveal>}
      <Reveal delay={0.05}>
        <h2 className="mt-5 font-display text-3xl font-bold tracking-tight text-white sm:text-4xl">{title}</h2>
      </Reveal>
      {subtitle && (
        <Reveal delay={0.1}>
          <p className="mt-4 text-base leading-relaxed text-zinc-400">{subtitle}</p>
        </Reveal>
      )}
    </div>
  )
}

/** The dark card surface every panel on this page shares. */
export const CARD =
  'rounded-2xl border border-white/[0.07] bg-[#0b0b0d]/80 backdrop-blur-xl ' +
  'shadow-[inset_0_1px_0_rgba(245,197,66,0.05),0_10px_40px_rgba(0,0,0,0.5)]'

export const CARD_HOVER =
  'transition-all duration-300 hover:-translate-y-1 hover:border-primary-500/35 ' +
  'hover:shadow-[0_18px_50px_rgba(212,175,55,0.14)]'

/** Round gold-tinted icon chip. */
export function IconChip({ icon: Icon, size = 44, className }) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full border border-primary-500/25 bg-primary-500/[0.09] text-primary-400',
        className,
      )}
      style={{ width: size, height: size }}
    >
      <Icon size={Math.round(size * 0.45)} />
    </span>
  )
}
