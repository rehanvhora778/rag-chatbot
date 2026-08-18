import { Link } from 'react-router-dom'
import { ArrowRight, GraduationCap, Mail } from 'lucide-react'
import { CARD, CARD_HOVER, Reveal, Section, SectionHeading } from './primitives'
import { PROJECT, AUTHOR } from '../landing/portfolio'

// Grouped by layer rather than one flat row of chips — it reads as an
// architecture summary instead of a keyword list, which is the question an
// examiner actually asks. Kept accurate to what production runs: embeddings go
// through ONNX Runtime, not sentence-transformers.
const STACK = [
  { group: 'Frontend', items: ['React + Vite', 'Tailwind CSS', 'Framer Motion'] },
  { group: 'Backend',  items: ['Django REST', 'JWT Auth', 'Gunicorn'] },
  { group: 'Data',     items: ['MongoDB', 'FAISS'] },
  { group: 'AI',       items: ['Groq LLM', 'ONNX Runtime', 'all-MiniLM-L6-v2'] },
]

export default function About() {
  return (
    <Section id="about" className="pb-28">
      <SectionHeading
        eyebrow="About"
        title={`Built by ${AUTHOR.name}`}
        subtitle={`${PROJECT.name} is a ${PROJECT.type.toLowerCase()} from ${PROJECT.college} — a working demonstration of Retrieval-Augmented Generation end to end.`}
      />

      <div className="mt-14 grid gap-5 lg:grid-cols-12">
        {/* Profile */}
        <Reveal className="lg:col-span-5">
          <article className={`${CARD} ${CARD_HOVER} flex h-full flex-col p-8`}>
            <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-primary-300 to-primary-600 font-display text-2xl font-bold text-ink-950">
              {AUTHOR.name[0]}
            </span>

            <h3 className="mt-6 font-display text-2xl font-bold tracking-tight text-white">
              {AUTHOR.name}
            </h3>
            <p className="mt-1 text-sm font-semibold text-primary-400">{AUTHOR.subtitle}</p>

            <p className="mt-5 text-sm leading-relaxed text-zinc-400">{AUTHOR.role}</p>

            <div className="mt-auto pt-8">
              <p className="flex items-center gap-2 border-t border-white/[0.07] pt-6 text-sm text-zinc-500">
                <GraduationCap size={16} className="shrink-0 text-primary-400" />
                {PROJECT.department} · {PROJECT.college}
              </p>
              <a
                href={`mailto:${PROJECT.email}`}
                className="mt-5 inline-flex items-center gap-2 rounded-xl border border-white/12 px-4 py-2.5 text-sm font-semibold text-zinc-200 transition-colors hover:border-primary-500/40 hover:text-white"
              >
                <Mail size={15} /> Get in touch
              </a>
            </div>
          </article>
        </Reveal>

        {/* Stack */}
        <Reveal delay={0.08} className="lg:col-span-7">
          <article className={`${CARD} h-full p-8`}>
            <h3 className="font-display text-xl font-semibold text-white">Under the hood</h3>
            <p className="mt-2 text-sm leading-relaxed text-zinc-500">
              Every layer built and deployed from scratch — no hosted RAG service in between.
            </p>

            <dl className="mt-8 space-y-6">
              {STACK.map(({ group, items }) => (
                <div key={group} className="sm:flex sm:items-baseline sm:gap-6">
                  <dt className="w-24 shrink-0 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                    {group}
                  </dt>
                  <dd className="mt-2 flex flex-wrap gap-2 sm:mt-0">
                    {items.map(t => (
                      <span
                        key={t}
                        className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-zinc-300"
                      >
                        {t}
                      </span>
                    ))}
                  </dd>
                </div>
              ))}
            </dl>
          </article>
        </Reveal>
      </div>

      {/* Closing call to action — the page used to end on the Docs section, so
          this keeps a way in rather than trailing off after the stack list. */}
      <Reveal delay={0.1}>
        <div className={`${CARD} mt-10 flex flex-col items-center gap-5 p-10 text-center`}>
          <h3 className="font-display text-2xl font-bold text-white sm:text-3xl">
            Ready to chat with your documents?
          </h3>
          <p className="max-w-md text-sm leading-relaxed text-zinc-400">
            Create an account in under a minute — no card, no setup.
          </p>
          <Link
            to="/register"
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-b from-primary-300 via-primary-400 to-primary-500 px-7 py-3.5 text-[15px] font-semibold text-ink-950 shadow-[0_8px_28px_rgba(212,175,55,0.34)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_12px_38px_rgba(212,175,55,0.48)]"
          >
            Get Started <ArrowRight size={17} />
          </Link>
        </div>
      </Reveal>
    </Section>
  )
}
