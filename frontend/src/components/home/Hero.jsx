import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, Sparkles } from 'lucide-react'
import HeroVisual from './HeroVisual'
import { Eyebrow } from './primitives'

const fadeUp = {
  hidden: { opacity: 0, y: 22 },
  show: i => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, delay: 0.08 * i, ease: [0.22, 1, 0.36, 1] },
  }),
}

export default function Hero() {
  return (
    <section id="home" className="relative scroll-mt-24 px-5 pb-10 pt-[120px] sm:px-8 sm:pt-[132px]">
      <div className="mx-auto grid w-full max-w-7xl items-center gap-12 lg:grid-cols-[1.02fr_1fr]">
        {/* copy */}
        <div>
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={0}>
            <Eyebrow>
              <Sparkles size={13} className="fill-primary-400" />
              AI-Powered Document Assistant
            </Eyebrow>
          </motion.div>

          <motion.h1
            variants={fadeUp}
            initial="hidden"
            animate="show"
            custom={1}
            className="mt-7 font-display text-[2.75rem] font-bold leading-[1.06] tracking-tight text-white sm:text-6xl"
          >
            Chat smarter
            <br />
            with your
            <br />
            <span className="text-gradient-animated">documents</span>
          </motion.h1>

          <motion.p
            variants={fadeUp}
            initial="hidden"
            animate="show"
            custom={2}
            className="mt-6 max-w-lg text-base leading-relaxed text-zinc-400 sm:text-[1.05rem]"
          >
            RAG Chatbot helps you retrieve, understand, and interact with your documents
            using the power of Retrieval-Augmented Generation.
          </motion.p>

          <motion.div
            variants={fadeUp}
            initial="hidden"
            animate="show"
            custom={3}
            className="mt-9 flex flex-wrap items-center gap-4"
          >
            <Link
              to="/register"
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-b from-primary-300 via-primary-400 to-primary-500 px-7 py-3.5 text-[15px] font-semibold text-ink-950 shadow-[0_8px_28px_rgba(212,175,55,0.34)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_12px_38px_rgba(212,175,55,0.48)]"
            >
              Get Started <ArrowRight size={17} />
            </Link>
            <a
              href="#features"
              className="inline-flex items-center gap-2 rounded-xl border border-white/12 bg-white/[0.03] px-7 py-3.5 text-[15px] font-semibold text-zinc-200 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary-500/40 hover:text-white"
            >
              Explore Features
            </a>
          </motion.div>
        </div>

        {/* centrepiece */}
        <motion.div
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
        >
          <HeroVisual />
        </motion.div>
      </div>
    </section>
  )
}
