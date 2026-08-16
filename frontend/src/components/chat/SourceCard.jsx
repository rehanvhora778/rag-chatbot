import { FileText, FileType } from 'lucide-react'
import { cn } from '../../lib/utils'

/* The extension drives the icon; the API sends the display filename. */
function iconFor(name = '') {
  return name.split('.').pop()?.toLowerCase() === 'pdf' ? FileText : FileType
}

/**
 * One retrieved source behind an answer.
 *
 * Everything shown comes from the citation the RAG pipeline returns:
 * document_name, page_number, similarity_score and a 200-char excerpt. The page
 * is shown as a badge because it is the thing a reader actually needs — it tells
 * them where in the PDF to look. The raw cosine score means nothing to them, so
 * it stays on the hover tooltip as a rough percentage.
 */
export default function SourceCard({ source, onOpen, compact = false }) {
  const Icon = iconFor(source.document_name)
  const page = source.page_number
  const match = typeof source.similarity_score === 'number'
    ? Math.round(Math.max(0, Math.min(1, source.similarity_score)) * 100)
    : null

  return (
    <button
      type="button"
      onClick={() => onOpen?.(source)}
      title={`${source.document_name}${page ? ` — Page ${page}` : ''}${match != null ? ` · ${match}% match` : ''}`}
      className={cn(
        'group flex min-w-0 items-start gap-2 rounded-xl border text-left transition-all duration-200',
        'border-primary-500/40 bg-ink-900/75 shadow-[0_0_14px_rgba(212,175,55,0.08)]',
        'hover:-translate-y-0.5 hover:border-primary-500/70 hover:bg-primary-500/[0.09]',
        'hover:shadow-[0_6px_22px_rgba(212,175,55,0.22)] focus:outline-none focus-visible:border-primary-500/80',
        compact ? 'px-2.5 py-2' : 'px-3 py-2.5',
      )}
    >
      <Icon size={13} className="mt-0.5 shrink-0 text-primary-400/90" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[11.5px] font-medium leading-tight text-zinc-200 group-hover:text-primary-100">
          {source.document_name}
        </span>
        {page ? (
          <span className="mt-1.5 inline-flex items-center rounded-md bg-primary-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-primary-200 ring-1 ring-primary-500/30">
            Page {page}
          </span>
        ) : null}
      </span>
    </button>
  )
}
