import { Link } from 'react-router-dom'
import { ArrowRight, GraduationCap, Mail } from 'lucide-react'
import { CARD, CARD_HOVER, Reveal, Section, SectionHeading } from './primitives'
import { PROJECT, AUTHOR } from '../landing/portfolio'

export default function About() {
  return (
    <Section id="about" className="pb-28">
      <SectionHeading
        eyebrow="About"
        title={`Built by ${AUTHOR.name}`}
        subtitle={`${PROJECT.name} is a ${PROJECT.type.toLowerCase()} from ${PROJECT.college} — a working demonstration of Retrieval-Augmented Generation end to end.`}
      />

      {/* One author, so this is a single horizontal card capped at max-w-3xl
          rather than a card stranded in one column of a wider grid. */}
      <div className="mt-14 flex justify-center">
        <Reveal className="w-full max-w-3xl">
          <article className={`${CARD} ${CARD_HOVER} p-8 sm:p-10`}>
            <div className="flex flex-col gap-7 sm:flex-row sm:items-start sm:gap-8">
              <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-primary-300 to-primary-600 font-display text-3xl font-bold text-ink-950">
                {AUTHOR.name[0]}
              </span>

              <div className="min-w-0 flex-1">
                <h3 className="font-display text-2xl font-bold tracking-tight text-white">
                  {AUTHOR.name}
                </h3>
                <p className="mt-1 text-sm font-semibold text-primary-400">{AUTHOR.subtitle}</p>

                <p className="mt-5 text-[15px] leading-relaxed text-zinc-400">{AUTHOR.role}</p>

                <div className="mt-7 flex flex-col gap-5 border-t border-white/[0.07] pt-6 sm:flex-row sm:items-center sm:justify-between">
                  <p className="flex items-center gap-2 text-sm text-zinc-500">
                    <GraduationCap size={16} className="shrink-0 text-primary-400" />
                    {PROJECT.department} · {PROJECT.college}
                  </p>
                  <a
                    href={`mailto:${PROJECT.email}`}
                    className="inline-flex shrink-0 items-center gap-2 self-start rounded-xl border border-white/12 px-4 py-2.5 text-sm font-semibold text-zinc-200 transition-colors hover:border-primary-500/40 hover:text-white sm:self-auto"
                  >
                    <Mail size={15} /> Get in touch
                  </a>
                </div>
              </div>
            </div>
          </article>
        </Reveal>
      </div>

      {/* Closing call to action — the page used to end on the Docs section, so
          this keeps a way in rather than trailing off after the profile. */}
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
