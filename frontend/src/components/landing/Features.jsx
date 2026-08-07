import {
  Files, Search, Layers, Quote, Zap, History, NotebookPen, ShieldCheck, Component,
} from 'lucide-react'
import { Section, Container, SectionHeading } from './common'
import Reveal from '../ui/Reveal'

const FEATURES = [
  { icon: Files,       title: 'Multi-document Chat',  desc: 'Query across many documents at once; retrieval spans your whole library.', g: 'from-primary-500 to-accent-600' },
  { icon: Search,      title: 'Semantic Search',      desc: 'Vector similarity search over meaning, not just keywords.',               g: 'from-emerald-500 to-teal-600' },
  { icon: Layers,      title: 'Hybrid Retrieval',     desc: 'Combines semantic and keyword signals for stronger recall.',              g: 'from-teal-500 to-emerald-600' },
  { icon: Quote,       title: 'Source Citations',     desc: 'Every answer links to the exact chunk, file and page it came from.',      g: 'from-violet-500 to-purple-600' },
  { icon: Zap,         title: 'Streaming Responses',  desc: 'Tokens stream in real time from Groq for instant feedback.',              g: 'from-amber-500 to-orange-600' },
  { icon: NotebookPen, title: 'AI Summaries',         desc: 'Generate structured summaries of long documents on demand.',              g: 'from-fuchsia-500 to-pink-600' },
  { icon: History,     title: 'Conversation History', desc: 'Sessions are persisted so you can resume any chat where you left off.',   g: 'from-rose-500 to-pink-600' },
  { icon: ShieldCheck, title: 'Authentication',       desc: "JWT-secured accounts keep each user's documents and chats isolated.",     g: 'from-green-500 to-emerald-600' },
]

export default function Features() {
  return (
    <Section id="features">
      <Container>
        <SectionHeading
          eyebrow="Core Features"
          eyebrowIcon={Component}
          title={<>Engineered for <span className="text-brand-gradient">real document workflows</span></>}
          subtitle="The capabilities that make the system genuinely useful, and genuinely technical."
        />

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <Reveal key={f.title} delay={(i % 3) * 0.06}>
              <div className="lp-card lp-card-hover spotlight-card group h-full p-5">
                <div className={`mb-3 inline-flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br ${f.g} text-white shadow-glow-sm transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-3`}>
                  <f.icon size={20} />
                </div>
                <h3 className="font-display text-base font-semibold lp-h">{f.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed lp-sub">{f.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </Container>
    </Section>
  )
}
