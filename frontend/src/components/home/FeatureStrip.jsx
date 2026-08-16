import { FileStack, ShieldCheck, Sparkles, Zap } from 'lucide-react'
import { CARD, IconChip, Reveal } from './primitives'

const ITEMS = [
  { icon: ShieldCheck, title: 'Secure & Private', body: 'Your data is safe and encrypted' },
  { icon: Sparkles,    title: 'AI-Powered',      body: 'Advanced RAG technology' },
  { icon: FileStack,   title: 'Multi-Format',    body: 'Support for PDF, DOCX and TXT files' },
  { icon: Zap,         title: 'Lightning Fast',  body: 'Get accurate answers instantly' },
]

/** The four-up reassurance bar that sits directly under the hero. */
export default function FeatureStrip() {
  return (
    <div className="px-5 pb-6 pt-8 sm:px-8">
      <Reveal className="mx-auto w-full max-w-7xl">
        <div className={`${CARD} grid gap-6 p-6 sm:grid-cols-2 sm:p-7 lg:grid-cols-4`}>
          {ITEMS.map(({ icon, title, body }) => (
            <div key={title} className="flex items-start gap-3.5">
              <IconChip icon={icon} size={42} />
              <div>
                <p className="text-[15px] font-semibold text-white">{title}</p>
                <p className="mt-1 text-[13px] leading-relaxed text-zinc-500">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </Reveal>
    </div>
  )
}
