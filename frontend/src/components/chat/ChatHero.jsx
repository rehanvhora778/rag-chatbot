import { motion } from 'framer-motion'
import { Target, Quote, Layers } from 'lucide-react'

const BADGES = [
  { icon: Target, label: 'Accurate Answers' },
  { icon: Quote,  label: 'Source Citations' },
  { icon: Layers, label: 'Multi-Document Support' },
]

/**
 * Animated RAG visualisation — three document sheets on the left feeding a
 * pulsing core on the right. Pure SVG/CSS, no raster asset, and it degrades to
 * a still image under prefers-reduced-motion (handled globally in index.css).
 */
function RagVisual() {
  return (
    <svg viewBox="0 0 220 120" className="h-full w-full" aria-hidden focusable="false">
      <defs>
        <linearGradient id="hero-gold" x1="0" y1="0" x2="220" y2="120" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#F5C542" />
          <stop offset="55%"  stopColor="#D4AF37" />
          <stop offset="100%" stopColor="#8E6F20" />
        </linearGradient>
        <radialGradient id="hero-core">
          <stop offset="0%"   stopColor="#F7E7A8" />
          <stop offset="55%"  stopColor="#F5C542" />
          <stop offset="100%" stopColor="#B8912B" />
        </radialGradient>
      </defs>

      {/* Document sheets */}
      {[18, 46, 74].map((y, i) => (
        <motion.g
          key={y}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 + i * 0.12, duration: 0.5 }}
        >
          <rect x="14" y={y} width="34" height="26" rx="4"
                fill="#101013" stroke="url(#hero-gold)" strokeWidth="1.1" opacity="0.85" />
          <path d={`M20 ${y + 8}h20M20 ${y + 13}h22M20 ${y + 18}h14`}
                stroke="url(#hero-gold)" strokeWidth="1.4" strokeLinecap="round" opacity="0.5" />
        </motion.g>
      ))}

      {/* Retrieval paths. The travelling packets use SMIL <animateMotion>
          rather than a CSS offset-path, which renders consistently across
          browsers without a JS animation frame per dot. */}
      {[31, 59, 87].map((y, i) => (
        <g key={y}>
          <path d={`M50 ${y} C 90 ${y}, 110 60, 150 60`}
                stroke="url(#hero-gold)" strokeWidth="1.1" fill="none" opacity="0.28" />
          <circle r="2.1" cx="0" cy="0" fill="#F5C542">
            <animateMotion
              dur="2.4s"
              begin={`${i * 0.7}s`}
              repeatCount="indefinite"
              path={`M50 ${y} C 90 ${y}, 110 60, 150 60`}
            />
            <animate
              attributeName="opacity"
              values="0;1;1;0"
              dur="2.4s"
              begin={`${i * 0.7}s`}
              repeatCount="indefinite"
            />
          </circle>
        </g>
      ))}

      {/* Core — the grounded answer. `r` and `opacity` are SVG attributes rather
          than style properties, so framer-motion has no implicit starting value
          for them: without an explicit `initial` it writes r="undefined" on the
          first frame and the browser rejects the attribute. */}
      <motion.circle
        cx="163" cy="60" r="23"
        fill="none" stroke="url(#hero-gold)" strokeWidth="1"
        initial={{ r: 23, opacity: 0.45 }}
        animate={{ r: [23, 30, 23], opacity: [0.45, 0.05, 0.45] }}
        transition={{ duration: 2.8, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.circle
        cx="163" cy="60" r="15"
        fill="url(#hero-core)"
        animate={{ scale: [1, 1.07, 1] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
        style={{ transformOrigin: '163px 60px' }}
      />
      <path d="M163 49 172 60 163 71 154 60Z" fill="#0A0A0C" opacity="0.35" />
    </svg>
  )
}

export default function ChatHero() {
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className="surface-gold relative mx-auto mb-6 w-full max-w-3xl overflow-hidden p-5 sm:p-6"
    >
      {/* Soft light behind the hero */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(ellipse 70% 130% at 88% 45%, rgba(212,175,55,0.16), transparent 68%)' }}
      />

      <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-xl font-bold leading-tight tracking-tight sm:text-2xl">
            <span className="text-gradient-animated">Your Intelligent Document Assistant</span>
          </h2>
          <p className="mt-2 max-w-lg text-[13px] leading-relaxed text-zinc-400">
            Upload your documents and get accurate, context-aware answers powered by
            Retrieval Augmented Generation.
          </p>

          <div className="mt-4 flex flex-wrap gap-2">
            {BADGES.map(({ icon: Icon, label }) => (
              <span key={label} className="chip">
                <Icon size={11} className="text-primary-400" />
                {label}
              </span>
            ))}
          </div>
        </div>

        <div className="h-24 w-full shrink-0 sm:h-28 sm:w-56">
          <RagVisual />
        </div>
      </div>
    </motion.section>
  )
}
