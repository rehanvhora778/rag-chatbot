import { useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useMotionValue, useSpring, useTransform, useReducedMotion } from 'framer-motion'
import { Rocket, Terminal } from 'lucide-react'
import AnimatedButton from '../ui/AnimatedButton'
import AuroraBackground from '../ui/AuroraBackground'
import ParticleBackground from '../ui/ParticleBackground'
import RagPipeline from './RagPipeline'
import { Container } from './common'
import { useAuth } from '../../contexts/AuthContext'
import { APP_ENTRY } from './portfolio'

const HEADLINE = ['AI-Powered', 'Document']
const TECH = ['React', 'Python', 'Django', 'MongoDB', 'FAISS', 'Groq', 'Llama 3.3', 'JWT', 'Tailwind CSS', 'Sentence Transformers']

export default function Hero() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const reduce = useReducedMotion()
  const ref = useRef(null)

  const mx = useMotionValue(0)
  const my = useMotionValue(0)
  const sx = useSpring(mx, { stiffness: 60, damping: 18 })
  const sy = useSpring(my, { stiffness: 60, damping: 18 })
  const auroraX = useTransform(sx, v => v * 36)
  const auroraY = useTransform(sy, v => v * 36)

  const onMove = e => {
    if (reduce || !ref.current) return
    const r = ref.current.getBoundingClientRect()
    mx.set((e.clientX - r.left) / r.width - 0.5)
    my.set((e.clientY - r.top) / r.height - 0.5)
  }

  return (
    <section
      id="home"
      ref={ref}
      onMouseMove={onMove}
      className="relative flex min-h-[100dvh] snap-start snap-always items-center overflow-hidden px-5 pb-12 pt-24 sm:px-8"
    >
      <div className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-violet-50/70 via-white to-white dark:from-transparent dark:via-transparent dark:to-transparent" />
      <motion.div style={{ x: auroraX, y: auroraY }} className="absolute inset-0 -z-10 opacity-70 dark:opacity-100">
        <AuroraBackground />
      </motion.div>
      <ParticleBackground count={26} className="-z-10" />

      <Container className="grid items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
        {/* ── copy ── */}
        <div className="text-center lg:text-left">
          <motion.span
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="lp-eyebrow"
          >
            <Terminal size={13} /> Full-Stack GenAI · Retrieval-Augmented Generation
          </motion.span>

          <h1 className="mt-5 font-display text-3xl font-bold uppercase leading-[1.05] tracking-tight lp-h sm:text-4xl lg:text-[2.9rem]">
            {HEADLINE.map((w, i) => (
              <motion.span
                key={i}
                initial={{ opacity: 0, y: 24, filter: 'blur(8px)' }}
                animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                transition={{ duration: 0.6, delay: 0.1 + i * 0.08, ease: [0.22, 1, 0.36, 1] }}
                className="mr-[0.28em] inline-block"
              >
                {w}
              </motion.span>
            ))}
            <motion.span
              initial={{ opacity: 0, y: 24, filter: 'blur(8px)' }}
              animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
              transition={{ duration: 0.6, delay: 0.26, ease: [0.22, 1, 0.36, 1] }}
              className="inline-block text-brand-gradient"
            >
              Intelligence
            </motion.span>
          </h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.5 }}
            className="mx-auto mt-6 max-w-xl text-base leading-relaxed lp-sub sm:text-lg lg:mx-0"
          >
            Upload documents and ask questions in natural language using Retrieval-Augmented Generation —
            powered by <span className="font-semibold lp-h">Llama 3.3</span>,{' '}
            <span className="font-semibold lp-h">FAISS</span> and{' '}
            <span className="font-semibold lp-h">Sentence Transformers</span>.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.65 }}
            className="mt-6 flex flex-col items-center gap-3 sm:flex-row lg:justify-start"
          >
            <AnimatedButton size="lg" className="w-full sm:w-auto" onClick={() => navigate(user ? '/dashboard' : APP_ENTRY)}>
              <Rocket size={17} /> Launch Application
            </AnimatedButton>
          </motion.div>

          {/* tech badges */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.85 }}
            className="mt-6 flex flex-wrap justify-center gap-2 lg:justify-start"
          >
            {TECH.map((t, i) => (
              <motion.span
                key={t}
                initial={{ opacity: 0, scale: 0.85 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.9 + i * 0.04 }}
                className="lp-pill"
              >
                {t}
              </motion.span>
            ))}
          </motion.div>
        </div>

        {/* ── animated RAG pipeline ── */}
        <motion.div
          initial={{ opacity: 0, scale: 0.94, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="relative mx-auto w-full max-w-md lg:max-w-none"
        >
          <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-gradient-to-tr from-primary-500/20 via-accent-500/10 to-emerald-500/10 blur-2xl" />
          <RagPipeline />
        </motion.div>
      </Container>

      {/* scroll cue */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.4 }}
        className="pointer-events-none absolute bottom-6 left-1/2 -translate-x-1/2"
      >
        <motion.div
          animate={{ y: [0, 8, 0] }}
          transition={{ duration: 1.6, repeat: Infinity }}
          className="flex h-9 w-5 items-start justify-center rounded-full border-2 border-zinc-300 p-1 dark:border-white/20"
        >
          <span className="h-1.5 w-1 rounded-full bg-zinc-400 dark:bg-white/50" />
        </motion.div>
      </motion.div>
    </section>
  )
}
