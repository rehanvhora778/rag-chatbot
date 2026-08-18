import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import { FileText, Plus, ChevronRight, ArrowRight } from 'lucide-react'
import LoadingSkeleton from '../ui/LoadingSkeleton'

/* Slice colours: the brightest gold goes to the biggest share, then down the
   ramp, with a neutral for the "Other" bucket. */
const SLICE_COLORS = ['#F5C542', '#D4AF37', '#B07E28', '#8E6F20']
const OTHER_COLOR  = '#3F3F46'

function timeAgo(iso) {
  if (!iso) return ''
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (Number.isNaN(secs)) return ''
  if (secs < 3600)   return `${Math.max(1, Math.floor(secs / 60))}m ago`
  if (secs < 86400)  return `${Math.floor(secs / 3600)}h ago`
  if (secs < 172800) return 'yesterday'
  return `${Math.floor(secs / 86400)}d ago`
}

function Panel({ title, action, children }) {
  return (
    <section className="panel-gold">
      <div className="flex items-center justify-between gap-2 px-4 pb-2.5 pt-3.5">
        <h3 className="min-w-0 truncate font-display text-[14px] font-bold text-white">{title}</h3>
        {action}
      </div>
      <div className="px-4 pb-4">{children}</div>
    </section>
  )
}

/**
 * "Knowledge Overview" donut.
 *
 * Shares are the real page counts of the user's own documents — the top four by
 * page count, with everything else folded into "Other". Nothing is estimated;
 * if a document reports no pages it simply contributes nothing to the ring.
 */
function KnowledgeDonut({ documents }) {
  const { slices, totalPages } = useMemo(() => {
    const withPages = documents
      .filter(d => (d.page_count || 0) > 0)
      .sort((a, b) => b.page_count - a.page_count)

    const total = withPages.reduce((n, d) => n + d.page_count, 0)
    if (!total) return { slices: [], totalPages: 0 }

    const top = withPages.slice(0, 4).map(d => ({
      name: (d.original_filename || '').replace(/\.[^.]+$/, ''),
      value: d.page_count,
    }))
    const rest = withPages.slice(4).reduce((n, d) => n + d.page_count, 0)
    if (rest > 0) top.push({ name: 'Other', value: rest, other: true })

    return { slices: top, totalPages: total }
  }, [documents])

  if (!slices.length) {
    return (
      <p className="py-6 text-center text-[12px] leading-relaxed text-zinc-600">
        Page counts appear here once a document finishes processing.
      </p>
    )
  }

  return (
    <div className="flex items-center gap-3">
      <div className="relative h-[124px] w-[124px] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={40}
              outerRadius={60}
              startAngle={90}
              endAngle={-270}
              paddingAngle={2}
              stroke="none"
              isAnimationActive={false}
            >
              {slices.map((s, i) => (
                <Cell key={i} fill={s.other ? OTHER_COLOR : SLICE_COLORS[i % SLICE_COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-display text-[22px] font-bold leading-none text-white">{totalPages}</span>
          <span className="mt-1 text-[9px] font-medium text-zinc-500">Total Pages</span>
        </div>
      </div>

      <ul className="min-w-0 flex-1 space-y-1.5">
        {slices.map((s, i) => (
          <li key={i} className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-[3px]"
              style={{ background: s.other ? OTHER_COLOR : SLICE_COLORS[i % SLICE_COLORS.length] }}
            />
            <span className="min-w-0 flex-1 truncate text-[11.5px] text-zinc-300" title={s.name}>
              {s.name}
            </span>
            <span className="shrink-0 text-[11px] tabular-nums text-zinc-500">
              {Math.round((s.value / totalPages) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* One "label — value" line in the Engine panel. */
function InfoRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="shrink-0 text-[12px] text-zinc-400">{label}</span>
      <span
        title={value}
        className="min-w-0 truncate rounded-lg border border-primary-500/30 bg-primary-500/[0.05] px-2.5 py-1.5 text-right font-geist text-[11.5px] text-zinc-300"
      >
        {value}
      </span>
    </div>
  )
}

/**
 * Right rail of the chat workspace: what's in the knowledge base, and what the
 * engine is running.
 *
 * Nothing here is editable — the model and retrieval settings are server-side
 * constants, so the panel reports them rather than pretending they are choices.
 */
export default function ChatRightPanel({
  documents = [],
  loading = false,
  config,
  onAddDocument,
}) {
  const recent = documents.slice(0, 5)

  return (
    <div className="flex h-full flex-col gap-3.5 overflow-y-auto p-3.5">
      {/* ── Uploaded Documents ── */}
      <Panel
        title="Uploaded Documents"
        action={
          <button
            onClick={onAddDocument}
            className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-primary-500/40 px-2.5 py-1.5 text-[11px] font-semibold text-primary-300 transition-colors hover:bg-primary-500/10"
          >
            <Plus size={12} strokeWidth={3} /> Add Document
          </button>
        }
      >
        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2].map(i => <LoadingSkeleton key={i} className="h-12 w-full rounded-xl" />)}
          </div>
        ) : recent.length === 0 ? (
          <p className="py-6 text-center text-[12px] leading-relaxed text-zinc-600">
            No documents yet. Upload one to start asking questions.
          </p>
        ) : (
          <>
            <ul className="space-y-1.5">
              {recent.map(d => (
                <li key={d.id}>
                  <Link
                    to="/documents"
                    className="row-gold group flex items-center gap-2.5 px-2.5 py-2"
                  >
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-500/[0.12] ring-1 ring-primary-500/30">
                      <FileText size={14} className="text-primary-400" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] font-medium text-zinc-200 group-hover:text-primary-100">
                        {d.original_filename}
                      </span>
                      <span className="mt-0.5 block truncate text-[10px] text-zinc-500">
                        {d.page_count ? `${d.page_count} page${d.page_count === 1 ? '' : 's'} • ` : ''}
                        Uploaded {timeAgo(d.created_at)}
                      </span>
                    </span>
                    <ChevronRight size={14} className="shrink-0 text-primary-500/50 transition-all group-hover:translate-x-0.5 group-hover:text-primary-400" />
                  </Link>
                </li>
              ))}
            </ul>
            <Link
              to="/documents"
              className="group mt-1.5 flex items-center justify-end gap-1 px-2 py-1 text-[11.5px] font-semibold text-primary-400 transition-colors hover:text-primary-300"
            >
              View all documents
              <ArrowRight size={12} className="transition-transform group-hover:translate-x-0.5" />
            </Link>
          </>
        )}
      </Panel>

      {/* ── Knowledge Overview ── */}
      <Panel title="Knowledge Overview">
        {loading
          ? <LoadingSkeleton className="h-[124px] w-full rounded-xl" />
          : <KnowledgeDonut documents={documents} />}
      </Panel>

      {/* ── Engine (read-only) ── */}
      <Panel title="Engine">
        {!config ? (
          <LoadingSkeleton className="h-24 w-full rounded-xl" />
        ) : (
          <div className="space-y-2">
            <InfoRow label="Model"     value={config.model} />
            <InfoRow label="Embedding" value={config.embedding_model} />
            <InfoRow label="Passages"  value={`Top ${config.retrieval.top_k} per question`} />
            <p className="pt-1 text-[10.5px] leading-relaxed text-zinc-600">
              Configured on the server, so every conversation answers the same way.
            </p>
          </div>
        )}
      </Panel>
    </div>
  )
}
