import { Link } from 'react-router-dom'
import { ArrowRight, BookOpen, KeyRound, Server, Terminal } from 'lucide-react'
import { CARD, CARD_HOVER, IconChip, Reveal, Section, SectionHeading } from './primitives'

const CARDS = [
  {
    icon: Terminal,
    title: 'Run it locally',
    body: 'Start the API with `python manage.py runserver` and the UI with `npm run dev`, then open localhost:3000.',
  },
  {
    icon: Server,
    title: 'What powers it',
    body: 'Django REST + MongoDB for data, FAISS for vector search, and Groq for answer generation.',
  },
  {
    icon: KeyRound,
    title: 'Signing in',
    body: 'Register with an email and password, or continue with your Google account. Admins sign in at /admin-login.',
  },
  {
    icon: BookOpen,
    title: 'Supported files',
    body: 'PDF (including scanned pages via OCR), DOCX and TXT — every answer cites the page it came from.',
  },
]

export default function Docs() {
  return (
    <Section id="docs" className="pb-28">
      <SectionHeading
        eyebrow="Docs"
        title="Getting started"
        subtitle="The short version — everything you need to run the project and understand what it does."
      />

      <div className="mt-14 grid gap-5 sm:grid-cols-2">
        {CARDS.map(({ icon, title, body }, i) => (
          <Reveal key={title} delay={i * 0.07}>
            <article className={`${CARD} ${CARD_HOVER} flex h-full items-start gap-4 p-6`}>
              <IconChip icon={icon} size={46} />
              <div>
                <h3 className="font-display text-lg font-semibold text-white">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-zinc-500">{body}</p>
              </div>
            </article>
          </Reveal>
        ))}
      </div>

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
