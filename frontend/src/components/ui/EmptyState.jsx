import { motion } from 'framer-motion'
import { cn } from '../../lib/utils'

/**
 * Shared empty / zero-data state.
 *
 * `actions` is rendered as-is so each caller supplies real buttons or links —
 * this component never invents a call to action.
 */
export default function EmptyState({
  icon: Icon,
  title,
  description,
  actions,
  className,
  compact = false,
}) {
  return (
    <div className={cn('relative overflow-hidden rounded-2xl text-center', compact ? 'px-6 py-10' : 'px-6 py-16', className)}>
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(ellipse 60% 70% at 50% 0%, rgba(212,175,55,0.09), transparent 70%)' }}
      />

      {Icon && (
        <motion.div
          animate={{ y: [0, -7, 0] }}
          transition={{ duration: 3.6, repeat: Infinity, ease: 'easeInOut' }}
          className="relative mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-primary-500/25 bg-primary-500/[0.08] shadow-glow-sm"
        >
          <Icon size={24} className="text-primary-400" />
        </motion.div>
      )}

      <h3 className="relative font-display text-base font-bold text-white sm:text-lg">{title}</h3>
      {description && (
        <p className="relative mx-auto mt-2 max-w-sm text-[13px] leading-relaxed text-zinc-500">{description}</p>
      )}
      {actions && <div className="relative mt-5 flex flex-wrap items-center justify-center gap-2.5">{actions}</div>}
    </div>
  )
}
