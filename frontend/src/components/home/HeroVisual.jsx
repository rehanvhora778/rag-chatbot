import { memo } from 'react'
import { motion } from 'framer-motion'
import { BrandMark } from '../brand/Brand'

/* The four formats that orbit the brain, with the tint each one is known by. */
const FORMATS = [
  { label: 'PDF',  tint: '#E5484D', pos: 'left-[2%] top-[16%]',    delay: 0 },
  { label: 'TXT',  tint: '#D8DEE9', pos: 'right-[2%] top-[12%]',   delay: 0.6 },
  { label: 'DOCX', tint: '#3B82F6', pos: 'left-[-2%] top-[46%]',   delay: 1.2 },
  { label: 'PPTX', tint: '#F97316', pos: 'right-[-2%] top-[44%]',  delay: 1.8 },
]

function FileCard({ label, tint, pos, delay }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1, y: [0, -12, 0] }}
      transition={{
        opacity: { duration: 0.5, delay: 0.3 + delay * 0.2 },
        scale: { duration: 0.5, delay: 0.3 + delay * 0.2 },
        y: { duration: 6, repeat: Infinity, ease: 'easeInOut', delay },
      }}
      className={`absolute ${pos} flex h-[68px] w-[62px] flex-col items-center justify-center gap-1 rounded-2xl border border-white/10 bg-[#0d0d10]/90 backdrop-blur-xl`}
      style={{ boxShadow: `0 10px 30px rgba(0,0,0,0.6), 0 0 22px ${tint}22` }}
    >
      {/* a document glyph tinted to the format */}
      <svg width="22" height="26" viewBox="0 0 22 26" fill="none" aria-hidden>
        <path d="M2 3a2 2 0 0 1 2-2h9l7 7v15a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V3Z" fill={tint} opacity="0.92" />
        <path d="M13 1l7 7h-5a2 2 0 0 1-2-2V1Z" fill="#fff" opacity="0.35" />
      </svg>
      <span className="text-[10px] font-bold tracking-wide text-zinc-300">{label}</span>
    </motion.div>
  )
}

/**
 * Hero centrepiece — a glowing brain on a lit pedestal, ringed by orbits, with
 * the supported document formats floating around it. Built from SVG + CSS so it
 * scales cleanly and ships no image assets.
 */
function HeroVisual() {
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[520px]">
      {/* ambient bloom */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(circle at 50% 44%, rgba(245,197,66,0.22), transparent 58%)' }}
      />

      {/* orbit rings */}
      <motion.div
        aria-hidden
        animate={{ rotate: 360 }}
        transition={{ duration: 42, repeat: Infinity, ease: 'linear' }}
        className="absolute inset-[8%]"
      >
        <svg viewBox="0 0 400 400" className="h-full w-full">
          <ellipse cx="200" cy="200" rx="192" ry="72" stroke="rgba(212,175,55,0.20)" strokeWidth="1" fill="none" />
          <ellipse cx="200" cy="200" rx="150" ry="150" stroke="rgba(212,175,55,0.12)" strokeWidth="1" fill="none" />
          <circle cx="392" cy="200" r="3" fill="#F5C542" opacity="0.8" />
          <circle cx="8" cy="200" r="2" fill="#F5C542" opacity="0.5" />
        </svg>
      </motion.div>
      <motion.div
        aria-hidden
        animate={{ rotate: -360 }}
        transition={{ duration: 60, repeat: Infinity, ease: 'linear' }}
        className="absolute inset-[16%]"
      >
        <svg viewBox="0 0 400 400" className="h-full w-full">
          <ellipse
            cx="200" cy="200" rx="180" ry="60"
            stroke="rgba(245,197,66,0.16)" strokeWidth="1" fill="none"
            transform="rotate(38 200 200)"
          />
        </svg>
      </motion.div>

      {/* sparks */}
      {[[18, 30], [78, 22], [88, 62], [12, 68], [64, 86], [34, 12]].map(([l, t], i) => (
        <motion.span
          key={i}
          aria-hidden
          className="absolute h-1 w-1 rounded-full bg-primary-300"
          style={{ left: `${l}%`, top: `${t}%` }}
          animate={{ opacity: [0.15, 0.85, 0.15], scale: [1, 1.6, 1] }}
          transition={{ duration: 2.6 + i * 0.4, repeat: Infinity, ease: 'easeInOut', delay: i * 0.35 }}
        />
      ))}

      {/* the brain */}
      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        className="absolute left-1/2 top-[42%] -translate-x-1/2 -translate-y-1/2"
      >
        <div
          aria-hidden
          className="absolute inset-0 -m-10 rounded-full blur-3xl"
          style={{ background: 'radial-gradient(circle, rgba(245,197,66,0.55), transparent 68%)' }}
        />
        <motion.div
          animate={{ y: [0, -10, 0] }}
          transition={{ duration: 7, repeat: Infinity, ease: 'easeInOut' }}
        >
          <BrandMark size={200} id="hero" stroke={1.6} className="relative drop-shadow-[0_0_28px_rgba(245,197,66,0.55)]" />
        </motion.div>
      </motion.div>

      {/* pedestal */}
      <div className="absolute bottom-[12%] left-1/2 w-[64%] -translate-x-1/2">
        <svg viewBox="0 0 320 96" className="w-full" aria-hidden>
          <defs>
            <linearGradient id="ped-rim" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#8E6F20" />
              <stop offset="50%" stopColor="#F5C542" />
              <stop offset="100%" stopColor="#8E6F20" />
            </linearGradient>
            <radialGradient id="ped-top" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#F7E7A8" stopOpacity="0.55" />
              <stop offset="100%" stopColor="#D4AF37" stopOpacity="0.05" />
            </radialGradient>
          </defs>
          <ellipse cx="160" cy="22" rx="86" ry="18" fill="url(#ped-top)" />
          <ellipse cx="160" cy="22" rx="86" ry="18" stroke="url(#ped-rim)" strokeWidth="1.5" fill="none" />
          <path d="M74 22a86 18 0 0 0 172 0v14a86 18 0 0 1-172 0Z" fill="#0d0b07" />
          <ellipse cx="160" cy="48" rx="116" ry="22" stroke="url(#ped-rim)" strokeWidth="1.2" fill="#0a0906" opacity="0.95" />
          <path d="M44 48a116 22 0 0 0 232 0v12a116 22 0 0 1-232 0Z" fill="#070605" />
          <ellipse cx="160" cy="76" rx="142" ry="16" fill="#D4AF37" opacity="0.08" />
        </svg>
      </div>

      {FORMATS.map(f => <FileCard key={f.label} {...f} />)}
    </div>
  )
}

export default memo(HeroVisual)
