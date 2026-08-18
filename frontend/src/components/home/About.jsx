import { GraduationCap, Github, Mail } from 'lucide-react'
import { CARD, CARD_HOVER, Reveal, Section, SectionHeading } from './primitives'
import { PROJECT, AUTHOR } from '../landing/portfolio'

const STACK = [
  'React + Vite', 'Tailwind CSS', 'Django REST', 'MongoDB',
  'FAISS', 'Sentence-Transformers', 'Groq LLM', 'JWT Auth',
]

export default function About() {
  return (
    <Section id="about">
      <SectionHeading
        eyebrow="About"
        title={`Built by ${AUTHOR.name}`}
        subtitle={`${PROJECT.name} is a ${PROJECT.type.toLowerCase()} from ${PROJECT.college} — a working demonstration of Retrieval-Augmented Generation end to end.`}
      />

      {/* One author, so the card is centred and capped rather than stranded in
          a three-column grid. */}
      <div className="mt-14 flex justify-center">
        <Reveal className="w-full max-w-md">
          <article className={`${CARD} ${CARD_HOVER} h-full p-6`}>
            <div className="flex items-center gap-4">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary-300 to-primary-600 font-display text-lg font-bold text-ink-950">
                {AUTHOR.name[0]}
              </span>
              <div>
                <p className="font-semibold text-white">{AUTHOR.name}</p>
                <p className="text-xs text-zinc-500">{AUTHOR.subtitle}</p>
              </div>
            </div>
            <p className="mt-4 text-sm text-zinc-400">{AUTHOR.role}</p>
          </article>
        </Reveal>
      </div>

      <Reveal delay={0.1}>
        <div className={`${CARD} mt-5 flex flex-col gap-6 p-7 md:flex-row md:items-center md:justify-between`}>
          <div>
            <p className="flex items-center gap-2 text-sm font-semibold text-primary-400">
              <GraduationCap size={16} /> {PROJECT.department} · {PROJECT.college}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {STACK.map(t => (
                <span key={t} className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-zinc-400">
                  {t}
                </span>
              ))}
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap gap-3">
            <a
              href={`mailto:${PROJECT.email}`}
              className="inline-flex items-center gap-2 rounded-xl border border-white/12 px-4 py-2.5 text-sm font-semibold text-zinc-200 transition-colors hover:border-primary-500/40 hover:text-white"
            >
              <Mail size={15} /> Email us
            </a>
            <a
              href="#docs"
              className="inline-flex items-center gap-2 rounded-xl border border-white/12 px-4 py-2.5 text-sm font-semibold text-zinc-200 transition-colors hover:border-primary-500/40 hover:text-white"
            >
              <Github size={15} /> Read the docs
            </a>
          </div>
        </div>
      </Reveal>
    </Section>
  )
}
