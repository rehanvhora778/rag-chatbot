import { Link } from 'react-router-dom'
import { Check } from 'lucide-react'
import { CARD, CARD_HOVER, Reveal, Section, SectionHeading } from './primitives'
import { cn } from '../../lib/utils'

const PLANS = [
  {
    name: 'Starter',
    price: 'Free',
    note: 'forever',
    blurb: 'Everything you need to try RAG on your own documents.',
    features: [
      'Up to 10 documents',
      '50 MB per file',
      'PDF, DOCX & TXT support',
      'Cited answers with sources',
      'Chat history',
    ],
    cta: 'Get Started',
  },
  {
    name: 'Pro',
    price: '₹499',
    note: '/ month',
    blurb: 'For heavy readers — bigger files and deeper analytics.',
    features: [
      'Unlimited documents',
      '50 MB per file',
      'Scanned-PDF OCR',
      'Document summaries & PDF export',
      'Usage analytics dashboard',
      'Priority processing',
    ],
    cta: 'Get Started',
    featured: true,
  },
  {
    name: 'Team',
    price: 'Custom',
    note: 'talk to us',
    blurb: 'Shared workspaces with central administration.',
    features: [
      'Everything in Pro',
      'Shared document library',
      'Admin console & user roles',
      'Self-hosted deployment',
      'Email support',
    ],
    cta: 'Contact Us',
  },
]

export default function Pricing() {
  return (
    <Section id="pricing">
      <SectionHeading
        eyebrow="Pricing"
        title="Simple, honest plans"
        subtitle="Start free. Upgrade only when your documents outgrow it."
      />

      <div className="mt-14 grid gap-5 lg:grid-cols-3">
        {PLANS.map((plan, i) => (
          <Reveal key={plan.name} delay={i * 0.08}>
            <article
              className={cn(
                CARD, CARD_HOVER,
                'relative flex h-full flex-col p-7',
                plan.featured && 'border-primary-500/40 shadow-[0_0_40px_rgba(212,175,55,0.12)]',
              )}
            >
              {plan.featured && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-gradient-to-b from-primary-300 to-primary-500 px-3 py-1 text-[11px] font-bold uppercase tracking-wide text-ink-950">
                  Most Popular
                </span>
              )}

              <p className="text-sm font-semibold uppercase tracking-wider text-primary-400">{plan.name}</p>
              <p className="mt-3 flex items-baseline gap-1.5">
                <span className="font-display text-4xl font-bold text-white">{plan.price}</span>
                <span className="text-sm text-zinc-500">{plan.note}</span>
              </p>
              <p className="mt-3 text-sm leading-relaxed text-zinc-500">{plan.blurb}</p>

              <ul className="mt-6 flex-1 space-y-3">
                {plan.features.map(f => (
                  <li key={f} className="flex items-start gap-2.5 text-sm text-zinc-300">
                    <Check size={15} className="mt-0.5 shrink-0 text-primary-400" />
                    {f}
                  </li>
                ))}
              </ul>

              <Link
                to="/register"
                className={cn(
                  'mt-7 inline-flex h-11 items-center justify-center rounded-xl text-sm font-semibold transition-all duration-200',
                  plan.featured
                    ? 'bg-gradient-to-b from-primary-300 via-primary-400 to-primary-500 text-ink-950 shadow-[0_6px_22px_rgba(212,175,55,0.3)] hover:shadow-[0_10px_32px_rgba(212,175,55,0.45)]'
                    : 'border border-white/12 text-zinc-200 hover:border-primary-500/40 hover:text-white',
                )}
              >
                {plan.cta}
              </Link>
            </article>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}
