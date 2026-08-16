import { MessagesSquare, Quote, Layers, Upload } from 'lucide-react'
import { CARD, CARD_HOVER, IconChip, Reveal, Section, SectionHeading } from './primitives'

const STEPS = [
  {
    icon: Upload,
    title: 'Upload your files',
    body: 'Drop in PDFs, Word documents or plain text files — up to 50 MB each.',
  },
  {
    icon: Layers,
    title: 'We index them',
    body: 'Text is extracted, split into overlapping chunks, embedded and stored in a FAISS vector index.',
  },
  {
    icon: MessagesSquare,
    title: 'Ask in plain language',
    body: 'Your question is embedded too, and the closest passages are retrieved as context.',
  },
  {
    icon: Quote,
    title: 'Get cited answers',
    body: 'The language model answers only from those passages, and shows you the sources it used.',
  },
]

export default function HowItWorks() {
  return (
    <Section id="how-it-works">
      <SectionHeading
        eyebrow="How It Works"
        title="From upload to answer in four steps"
        subtitle="Retrieval-Augmented Generation grounds every answer in your own documents instead of the model's memory."
      />

      <div className="relative mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {/* the thread that runs through the steps on wide screens */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-8 top-[58px] hidden h-px lg:block"
          style={{ background: 'linear-gradient(90deg, transparent, rgba(212,175,55,0.35), rgba(212,175,55,0.35), transparent)' }}
        />

        {STEPS.map(({ icon, title, body }, i) => (
          <Reveal key={title} delay={i * 0.08}>
            <article className={`${CARD} ${CARD_HOVER} relative h-full p-6`}>
              <div className="flex items-center justify-between">
                <IconChip icon={icon} size={48} />
                <span className="font-display text-4xl font-bold text-white/[0.07]">0{i + 1}</span>
              </div>
              <h3 className="mt-5 font-display text-lg font-semibold text-white">{title}</h3>
              <p className="mt-2.5 text-sm leading-relaxed text-zinc-500">{body}</p>
            </article>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}
