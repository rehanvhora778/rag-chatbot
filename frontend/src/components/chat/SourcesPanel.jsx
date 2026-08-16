import { useState } from 'react'
import { ArrowRight } from 'lucide-react'
import Modal from '../common/Modal'
import SourceCard from './SourceCard'

const PREVIEW_COUNT = 3

/**
 * The "Sources" strip beneath an AI answer.
 *
 * Shows the first few citations inline and opens the rest — plus each source's
 * retrieved excerpt and match score — in a modal. Excerpts are what the model
 * actually read, so a user can check an answer against its evidence.
 */
export default function SourcesPanel({ sources = [] }) {
  const [allOpen, setAllOpen] = useState(false)
  const [detail, setDetail] = useState(null)

  if (!sources.length) return null

  const preview = sources.slice(0, PREVIEW_COUNT)
  // Every page this answer drew on, in document order — a one-line index of
  // where to look in the PDF.
  const pages = [...new Set(sources.map(s => s.page_number).filter(Boolean))]
    .sort((a, b) => a - b)

  return (
    // `data-sources` marks this block for the PDF export, which keeps it whole
    // rather than letting a page break slice through the cards.
    <div data-sources="" className="mt-4 border-t border-primary-500/20 pt-3">
      <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1">
        <p className="text-[11.5px] font-medium text-zinc-400">Sources:</p>
        {pages.length > 0 && (
          <p className="text-[11px] text-zinc-500">
            from page{pages.length > 1 ? 's' : ''}{' '}
            <span className="font-semibold text-primary-300">{pages.join(', ')}</span>
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {preview.map((s, i) => (
          <SourceCard key={`${s.document_id}-${s.page_number}-${i}`} source={s} onOpen={setDetail} />
        ))}
      </div>

      <button
        onClick={() => setAllOpen(true)}
        className="group mt-2.5 flex w-full items-center justify-end gap-1.5 text-[11.5px] font-semibold text-primary-400 transition-colors hover:text-primary-300"
      >
        Show all sources
        <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
      </button>

      {/* All sources */}
      <Modal open={allOpen} onClose={() => setAllOpen(false)} title="Sources for this answer" size="lg">
        <div className="space-y-2.5">
          {sources.map((s, i) => (
            <div key={`${s.document_id}-${s.page_number}-all-${i}`} className="rounded-xl border border-primary-500/25 bg-primary-500/[0.03] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-geist text-[10px] font-bold text-primary-500/80">[{i + 1}]</span>
                <span className="min-w-0 flex-1 truncate text-[12.5px] font-semibold text-zinc-200">{s.document_name}</span>
                {s.page_number ? <span className="chip shrink-0">Page {s.page_number}</span> : null}
                {typeof s.similarity_score === 'number' && (
                  <span className="chip shrink-0">{Math.round(s.similarity_score * 100)}% match</span>
                )}
              </div>
              {s.excerpt && (
                <p className="mt-2 border-l-2 border-primary-500/25 pl-3 text-[12px] leading-relaxed text-zinc-400">
                  {s.excerpt}
                </p>
              )}
            </div>
          ))}
        </div>
      </Modal>

      {/* Single source detail */}
      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail?.document_name || 'Source'} size="md">
        {detail && (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {detail.page_number ? <span className="chip">Page {detail.page_number}</span> : null}
              {typeof detail.similarity_score === 'number' && (
                <span className="chip">{Math.round(detail.similarity_score * 100)}% match</span>
              )}
            </div>
            <div>
              <p className="label">Retrieved excerpt</p>
              <p className="whitespace-pre-wrap rounded-xl border border-primary-500/25 bg-black/40 p-3.5 text-[13px] leading-relaxed text-zinc-300">
                {detail.excerpt || 'No excerpt was stored for this source.'}
              </p>
            </div>
            <p className="text-[11px] leading-relaxed text-zinc-600">
              This is the passage the assistant read when answering. It is a portion of the
              document, not the whole file.
            </p>
          </div>
        )}
      </Modal>
    </div>
  )
}
