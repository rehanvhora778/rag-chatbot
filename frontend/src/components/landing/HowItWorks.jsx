import { UploadCloud, FileText, Scissors, Boxes, Database, Search, Send, Sparkles, Quote, Workflow } from 'lucide-react'
import { Section, Container, SectionHeading } from './common'
import Reveal from '../ui/Reveal'
import SiteFooter from './SiteFooter'

const STEPS = [
  { icon: UploadCloud, title: 'Upload Document',   desc: 'PDFs, DOCX, slides, spreadsheets and more.' },
  { icon: FileText,    title: 'Extract Text',      desc: 'Parse text, with OCR fallback for scans.' },
  { icon: Scissors,    title: 'Split into Chunks', desc: 'Overlapping, semantically coherent chunks.' },
  { icon: Boxes,       title: 'Create Embeddings', desc: 'Encode chunks with Sentence Transformers.' },
  { icon: Database,    title: 'Store in FAISS',    desc: 'Index vectors for fast similarity search.' },
  { icon: Search,      title: 'Search Chunks',     desc: 'Embed the query, retrieve the top-k matches.' },
  { icon: Send,        title: 'Send Context',      desc: 'Inject retrieved context into the prompt.' },
  { icon: Sparkles,    title: 'Generate Answer',   desc: 'Llama 3.3 composes a grounded reply.' },
  { icon: Quote,       title: 'Show Citations',    desc: 'Link every claim back to its source.' },
]

export default function HowItWorks() {
  return (
    <Section id="how-rag" className="justify-between pb-0">
      <div className="flex w-full flex-1 flex-col justify-center">
        <Container>
        <SectionHeading
          eyebrow="How RAG Works"
          eyebrowIcon={Workflow}
          title={<>The pipeline, <span className="text-brand-gradient">step by step</span></>}
          subtitle="A transparent retrieval-then-generation flow, with no black boxes."
        />

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {STEPS.map((s, i) => (
            <Reveal key={s.title} delay={(i % 3) * 0.06}>
              <div className="lp-card lp-card-hover group h-full p-5">
                <div className="mb-3 flex items-center justify-between">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-accent-600 text-white shadow-glow-sm transition-transform duration-300 group-hover:scale-110">
                    <s.icon size={18} />
                  </span>
                  <span className="font-display text-lg font-bold text-primary-500/30 dark:text-primary-300/30">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                </div>
                <h3 className="font-display text-base font-semibold lp-h">{s.title}</h3>
                <p className="mt-1 text-sm leading-relaxed lp-sub">{s.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
        </Container>
      </div>

      {/* footer lives in the last viewport; break out of the section's x-padding */}
      <div className="-mx-5 sm:-mx-8">
        <SiteFooter />
      </div>
    </Section>
  )
}
