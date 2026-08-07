import { Atom, Wind, Code2, Server, Database, Boxes, Zap, Cpu, KeyRound, Layers3 } from 'lucide-react'
import { Section, Container as Wrap, SectionHeading } from './common'
import Reveal from '../ui/Reveal'

const TECH = [
  { icon: Atom,      name: 'React',         purpose: 'Frontend UI',          category: 'Frontend',   g: 'from-sky-500 to-cyan-600' },
  { icon: Wind,      name: 'Tailwind CSS',  purpose: 'Styling system',       category: 'Frontend',   g: 'from-teal-500 to-cyan-600' },
  { icon: Code2,     name: 'Python',        purpose: 'Backend language',     category: 'Backend',    g: 'from-blue-500 to-indigo-600' },
  { icon: Server,    name: 'Django REST',   purpose: 'REST API layer',       category: 'Backend',    g: 'from-emerald-500 to-green-600' },
  { icon: Database,  name: 'MongoDB',       purpose: 'Document data store',  category: 'Database',   g: 'from-green-500 to-emerald-600' },
  { icon: Boxes,     name: 'FAISS',         purpose: 'Vector search',        category: 'Retrieval',  g: 'from-violet-500 to-purple-600' },
  { icon: Zap,       name: 'Groq',          purpose: 'LLM inference',        category: 'Inference',  g: 'from-amber-500 to-orange-600' },
  { icon: Cpu,       name: 'Llama 3.3 70B', purpose: 'Generation model',     category: 'Model',      g: 'from-primary-500 to-accent-600' },
  { icon: KeyRound,  name: 'JWT',           purpose: 'Auth & sessions',      category: 'Security',   g: 'from-rose-500 to-red-600' },
]

export default function TechStack() {
  return (
    <Section id="tech-stack">
      <Wrap>
        <SectionHeading
          eyebrow="Tech Stack"
          eyebrowIcon={Layers3}
          title={<>The tools behind <span className="text-brand-gradient">the build</span></>}
          subtitle="A modern, production-grade stack spanning frontend, backend, data and AI."
        />

        <div className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {TECH.map((t, i) => (
            <Reveal key={t.name} delay={(i % 4) * 0.05}>
              <div className="lp-card lp-card-hover group flex h-full items-center gap-3 p-4">
                <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${t.g} text-white shadow-glow-sm transition-transform duration-300 group-hover:scale-110`}>
                  <t.icon size={18} />
                </span>
                <div className="min-w-0">
                  <h3 className="truncate font-display text-sm font-semibold lp-h">{t.name}</h3>
                  <p className="truncate text-xs lp-sub">{t.purpose}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </Wrap>
    </Section>
  )
}
