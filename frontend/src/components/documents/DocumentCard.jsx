import { useState, useRef, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  FileText, FileType2, MoreVertical, Eye, MessageSquare,
  Pencil, Trash2, CheckCircle, Clock, XCircle, Loader, AlertTriangle, RefreshCw,
} from 'lucide-react'
import { cn } from '../../lib/utils'

export const STATUS_META = {
  completed:  { icon: CheckCircle, badge: 'bg-success-500/[0.12] text-success-400 ring-1 ring-success-500/20', label: 'Ready' },
  processing: { icon: Loader,      badge: 'bg-primary-500/[0.12] text-primary-300 ring-1 ring-primary-500/25', label: 'Processing' },
  pending:    { icon: Clock,       badge: 'bg-white/[0.05] text-zinc-400 ring-1 ring-white/10',               label: 'Queued' },
  failed:     { icon: XCircle,     badge: 'bg-red-500/[0.12] text-red-400 ring-1 ring-red-500/20',            label: 'Failed' },
}

const formatDate = iso => {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function ActionsMenu({ doc, onView, onChat, onRename, onDelete, onReprocess }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDown = e => { if (!ref.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const ready = doc.status === 'completed'
  const run = fn => () => { setOpen(false); fn(doc) }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        aria-label="Document actions"
        aria-haspopup="menu"
        className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-primary-500/10 hover:text-primary-300"
      >
        <MoreVertical size={15} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, scale: 0.96, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: -3 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-xl border border-primary-500/20 bg-ink-850/[0.97] p-1.5 shadow-[0_16px_50px_rgba(0,0,0,0.7)] backdrop-blur-2xl"
          >
            {ready && (
              <>
                <button role="menuitem" onClick={run(onView)} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-zinc-300 transition-colors hover:bg-primary-500/10 hover:text-primary-200">
                  <Eye size={14} className="text-zinc-500" /> View details
                </button>
                <button role="menuitem" onClick={run(onChat)} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-zinc-300 transition-colors hover:bg-primary-500/10 hover:text-primary-200">
                  <MessageSquare size={14} className="text-zinc-500" /> Chat with document
                </button>
              </>
            )}
            {/* Offered for a failed document, and for a completed one after a
                chunking or embedding change. Not offered while it is already
                queued or running — a second job on the same document would
                just be redelivered work. */}
            {onReprocess && doc.status !== 'pending' && doc.status !== 'processing' && (
              <button role="menuitem" onClick={run(onReprocess)} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-zinc-300 transition-colors hover:bg-primary-500/10 hover:text-primary-200">
                <RefreshCw size={13} /> Reprocess
              </button>
            )}
            <button role="menuitem" onClick={run(onRename)} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-zinc-300 transition-colors hover:bg-primary-500/10 hover:text-primary-200">
              <Pencil size={14} className="text-zinc-500" /> Rename
            </button>
            <div className="my-1 h-px bg-white/[0.06]" />
            <button role="menuitem" onClick={run(onDelete)} className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-red-400 transition-colors hover:bg-red-500/10">
              <Trash2 size={14} /> Delete
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/**
 * One document in the grid.
 *
 * Every fact shown (pages, size, chunks, status, error) comes from the document
 * record the API returns — nothing is inferred or padded out.
 *
 * The card deliberately does not clip its overflow: the actions dropdown is
 * absolutely positioned below its trigger, and overflow-hidden cut the menu off
 * part way down. The shimmer overlay carries its own rounded-2xl, so it still
 * stays inside the corners without the card clipping.
 */
export default function DocumentCard({ doc, onView, onChat, onRename, onDelete, onReprocess, variants }) {
  const meta = STATUS_META[doc.status] || STATUS_META.pending
  const StatusIcon = meta.icon
  const busy = doc.status === 'processing' || doc.status === 'pending'

  return (
    <motion.div
      layout
      variants={variants}
      exit={{ opacity: 0, scale: 0.94 }}
      whileHover={{ y: -3 }}
      transition={{ type: 'spring', stiffness: 300, damping: 26 }}
      className="group relative flex flex-col rounded-2xl border border-white/[0.07] bg-ink-800/60 p-4 backdrop-blur-xl transition-colors hover:border-primary-500/30 sm:p-5"
    >
      {busy && <div className="shimmer pointer-events-none absolute inset-0 rounded-2xl" />}

      <div className="relative flex items-start justify-between gap-2">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500/20 to-accent-600/10 ring-1 ring-primary-500/20">
          <FileText size={18} className="text-primary-300" />
        </div>
        <div className="flex items-center gap-1">
          <span className={cn('badge shrink-0', meta.badge)}>
            <StatusIcon size={11} className={doc.status === 'processing' ? 'animate-spin' : ''} />
            {meta.label}
          </span>
          <ActionsMenu doc={doc} onView={onView} onChat={onChat} onRename={onRename} onDelete={onDelete} onReprocess={onReprocess} />
        </div>
      </div>

      <p className="relative mt-3.5 truncate text-sm font-semibold text-white" title={doc.original_filename}>
        {doc.original_filename}
      </p>

      <div className="relative mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-zinc-500">
        <span className="inline-flex items-center gap-1 uppercase"><FileType2 size={11} />{doc.file_type}</span>
        <span className="text-zinc-700">·</span>
        <span>{doc.file_size_display}</span>
        {doc.page_count ? (
          <><span className="text-zinc-700">·</span>
            <span>{doc.page_count} page{doc.page_count !== 1 ? 's' : ''}</span></>
        ) : null}
      </div>

      {doc.status === 'failed' && doc.error_message && (
        <div className="relative mt-3 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-2.5 py-2">
          <AlertTriangle size={12} className="mt-0.5 shrink-0 text-red-400" />
          <p className="text-[11px] leading-relaxed text-red-300/90">
            Unable to process this document. Please try uploading it again.
          </p>
        </div>
      )}

      <div className="relative mt-auto flex items-center justify-between gap-2 border-t border-white/[0.05] pt-3 text-[10px] text-zinc-600">
        <span>Uploaded {formatDate(doc.created_at)}</span>
        {doc.chunk_count ? <span>{doc.chunk_count} chunks indexed</span> : null}
      </div>
    </motion.div>
  )
}
