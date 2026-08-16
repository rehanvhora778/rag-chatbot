import { BarChart3, MessageCircle, Search, ShieldCheck } from 'lucide-react'
import { CARD, CARD_HOVER, IconChip, Reveal, Section, SectionHeading } from './primitives'

const FEATURES = [
  {
    icon: MessageCircle,
    title: 'Ask Anything',
    body: 'Get accurate answers from your documents using natural language.',
  },
  {
    icon: Search,
    title: 'Smart Retrieval',
    body: 'Advanced retrieval algorithms find the most relevant information.',
  },
  {
    icon: ShieldCheck,
    title: 'Secure & Private',
    body: 'Your documents are encrypted and never shared with anyone.',
  },
  {
    icon: BarChart3,
    title: 'Analytics',
    body: 'Track usage and discover insights from your documents.',
  },
]

export default function Features() {
  return (
    <Section id="features">
      <SectionHeading
        eyebrow="Powerful Features"
        title="Everything you need"
        subtitle="Powerful tools to help you get the most out of your documents."
      />

      <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map(({ icon, title, body }, i) => (
          <Reveal key={title} delay={i * 0.08}>
            <article className={`${CARD} ${CARD_HOVER} h-full p-6`}>
              <IconChip icon={icon} size={52} />
              <h3 className="mt-5 font-display text-lg font-semibold text-white">{title}</h3>
              <p className="mt-2.5 text-sm leading-relaxed text-zinc-500">{body}</p>
            </article>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}
