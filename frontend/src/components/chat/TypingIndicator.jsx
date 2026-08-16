import { motion } from 'framer-motion'
import Logo from '../ui/Logo'

const STAGES = ['Searching your documents', 'Reading the best passages', 'Composing the answer']

/**
 * Shown while the RAG request is in flight.
 *
 * The three labels mirror the actual server-side sequence (FAISS retrieval →
 * context assembly → Groq generation), but the endpoint reports no progress, so
 * they advance on a timer and are worded as activity rather than as a
 * percentage. Nothing here claims to know how far along the request is.
 */
export default function TypingIndicator({ stage = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="mb-6 flex gap-2.5 sm:gap-3"
    >
      <Logo size={32} id="typing" className="mt-0.5" />
      <div className="rounded-2xl rounded-tl-md border border-primary-500/25 bg-ink-900/80 px-4 py-3 shadow-[0_0_20px_rgba(212,175,55,0.10)] backdrop-blur-md">
        <div className="flex items-center gap-2.5">
          <span className="flex gap-1">
            {[0, 1, 2].map(i => (
              <motion.span
                key={i}
                className="h-1.5 w-1.5 rounded-full bg-primary-400"
                animate={{ opacity: [0.25, 1, 0.25], y: [0, -3, 0] }}
                transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.16, ease: 'easeInOut' }}
              />
            ))}
          </span>
          <motion.span
            key={stage}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-[12px] font-medium text-zinc-400"
          >
            {STAGES[Math.min(stage, STAGES.length - 1)]}…
          </motion.span>
        </div>
      </div>
    </motion.div>
  )
}
