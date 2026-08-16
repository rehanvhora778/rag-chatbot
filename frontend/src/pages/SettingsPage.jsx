import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Cpu, Database, Info } from 'lucide-react'
import toast from 'react-hot-toast'

import { chatAPI } from '../api/chat'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'

const item = {
  hidden: { opacity: 0, y: 16 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] } },
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-white/[0.05] py-2.5 last:border-0">
      <span className="min-w-0 text-[12px] text-zinc-400">{label}</span>
      <span className="shrink-0 font-geist text-[12px] font-medium text-zinc-200">{value}</span>
    </div>
  )
}

function Card({ icon: Icon, title, subtitle, note, children }) {
  return (
    <motion.section variants={item} className="surface-gold p-4 sm:p-5">
      <div className="mb-4 flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-500/10 ring-1 ring-primary-500/20">
          <Icon size={16} className="text-primary-400" />
        </span>
        <div>
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          <p className="text-[11px] text-zinc-500">{subtitle}</p>
        </div>
      </div>

      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-1">
        {children}
      </div>

      <p className="mt-2.5 flex items-start gap-1.5 text-[11px] leading-relaxed text-zinc-600">
        <Info size={11} className="mt-0.5 shrink-0" />
        {note}
      </p>
    </motion.section>
  )
}

/**
 * Settings — a read-only report of how the RAG engine is configured.
 *
 * Everything here is a server-side constant that applies to every conversation,
 * so the page shows what the pipeline does rather than offering controls. The
 * values are read live from /api/chat/config/, which returns them straight from
 * Django settings, so this page can never claim something the engine isn't
 * actually doing.
 */
export default function SettingsPage() {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    chatAPI.getConfig()
      .then(res => setConfig(res.data.data))
      .catch(() => toast.error('Could not load your configuration.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="space-y-2">
          <LoadingSkeleton className="h-7 w-40" />
          <LoadingSkeleton className="h-3 w-64" />
        </div>
        <LoadingSkeleton className="h-40 w-full rounded-2xl" />
        <LoadingSkeleton className="h-56 w-full rounded-2xl" />
      </div>
    )
  }

  if (!config) return null

  const r = config.retrieval

  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.06 } } }}
      className="mx-auto max-w-3xl space-y-6 pb-4"
    >
      <motion.div variants={item}>
        <h2 className="page-title">Settings</h2>
        <p className="page-subtitle">How your documents are read, searched and answered</p>
      </motion.div>

      <Card
        icon={Cpu}
        title="Model"
        subtitle="What is running behind your answers"
        note="Both models are configured on the server and are the same for every conversation."
      >
        <Row label="Generation model" value={config.model} />
        <Row label="Embedding model"  value={config.embedding_model} />
      </Card>

      <Card
        icon={Database}
        title="Retrieval pipeline"
        subtitle="How your documents are indexed and searched"
        note="Chunking and embedding happen at upload time, so changing these would mean
              re-indexing every document. They are fixed on the server to keep every answer
              consistent."
      >
        <Row label="Passages sent to the model" value={r.top_k} />
        <Row label="Chunk size"                 value={`${r.chunk_size} characters`} />
        <Row label="Chunk overlap"              value={`${r.chunk_overlap} characters`} />
        <Row label="Candidate pool (fetch K)"   value={r.fetch_k} />
        <Row label="MMR diversity"              value={r.use_mmr ? 'Enabled' : 'Disabled'} />
        <Row label="Minimum similarity"         value={r.min_similarity} />
        <Row label="Conversation memory"        value={`${r.memory_turns} turns`} />
      </Card>
    </motion.div>
  )
}
