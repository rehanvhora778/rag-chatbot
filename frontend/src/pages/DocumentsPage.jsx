import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { RefreshCw, Upload, FileText, Search, Trash2, BookOpen } from 'lucide-react'
import toast from 'react-hot-toast'

import { documentsAPI } from '../api/documents'
import { chatAPI } from '../api/chat'
import Modal from '../components/common/Modal'
import AnimatedButton from '../components/ui/AnimatedButton'
import EmptyState from '../components/ui/EmptyState'
import LoadingSkeleton, { SkeletonDocCard } from '../components/ui/LoadingSkeleton'
import DocumentCard, { STATUS_META } from '../components/documents/DocumentCard'
import DocumentUpload, { UploadResult } from '../components/documents/DocumentUpload'

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] } },
}

const SORTS = {
  newest: { label: 'Newest first',  fn: (a, b) => new Date(b.created_at) - new Date(a.created_at) },
  oldest: { label: 'Oldest first',  fn: (a, b) => new Date(a.created_at) - new Date(b.created_at) },
  name:   { label: 'Name (A–Z)',    fn: (a, b) => (a.original_filename || '').localeCompare(b.original_filename || '') },
  size:   { label: 'Largest first', fn: (a, b) => (b.file_size || 0) - (a.file_size || 0) },
}

function friendlyError(err, fallback) {
  const status = err?.response?.status
  if (status === 413) return 'That file is too large for the server to accept.'
  if (status === 401) return 'Your session expired. Please sign in again.'
  if (!err?.response) return 'Cannot reach the server. Check your connection and try again.'
  return err.response?.data?.message || fallback
}

export default function DocumentsPage() {
  const navigate = useNavigate()

  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [phase, setPhase] = useState('transfer')
  const [result, setResult] = useState(null)

  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sortKey, setSortKey] = useState('newest')

  const [detail, setDetail] = useState(null)
  const [summary, setSummary] = useState(null)
  const [renaming, setRenaming] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  // Held in a ref so the polling effect doesn't re-subscribe on every render.
  const docsRef = useRef(docs)
  useEffect(() => { docsRef.current = docs }, [docs])

  const fetchDocs = useCallback(({ silent = false } = {}) => {
    if (!silent) setLoading(true)
    return documentsAPI.list({ page: 1, page_size: 100 })
      .then(res => setDocs(res.data.data || []))
      .catch(err => { if (!silent) toast.error(friendlyError(err, 'Could not load your documents.')) })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetchDocs() }, [fetchDocs])

  /* Poll only while something is actually being processed. */
  useEffect(() => {
    const id = setInterval(() => {
      if (docsRef.current.some(d => d.status === 'pending' || d.status === 'processing')) {
        fetchDocs({ silent: true })
      }
    }, 4000)
    return () => clearInterval(id)
  }, [fetchDocs])

  const handleUpload = async files => {
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))

    setUploading(true)
    setProgress(0)
    setPhase('transfer')
    setResult(null)

    try {
      const res = await documentsAPI.upload(fd, evt => {
        if (!evt.total) return
        const pct = Math.round((evt.loaded / evt.total) * 100)
        setProgress(pct)
        // 100% transferred means the server now owns it — swap to the
        // indeterminate processing state rather than sitting at "100%".
        if (pct >= 100) setPhase('processing')
      })
      setResult({ ok: res.data.message, errors: res.data.data?.errors || [] })
      fetchDocs({ silent: true })
    } catch (err) {
      const errs = err.response?.data?.errors
      setResult({ ok: null, errors: Array.isArray(errs) ? errs : [friendlyError(err, 'Upload failed.')] })
    } finally {
      setUploading(false)
      setProgress(0)
      setPhase('transfer')
    }
  }

  const openDetail = async doc => {
    setDetail(doc)
    setSummary(null)
    try {
      const res = await documentsAPI.getSummary(doc.id)
      setSummary(res.data.data.summary || '')
    } catch {
      setSummary('__error__')
    }
  }

  const chatWithDoc = async doc => {
    try {
      const res = await chatAPI.createSession({ title: doc.original_filename, document_ids: [doc.id] })
      window.dispatchEvent(new Event('chat-sessions-changed'))
      navigate(`/chat/${res.data.data.id}`)
    } catch (err) {
      toast.error(friendlyError(err, 'Could not start a chat with that document.'))
    }
  }

  const submitRename = async () => {
    const name = renameValue.trim()
    if (!name || !renaming) return
    try {
      const res = await documentsAPI.rename(renaming.id, name)
      const updated = res.data.data
      setDocs(list => list.map(d => (d.id === updated.id ? updated : d)))
      toast.success('Document renamed.')
      setRenaming(null)
    } catch (err) {
      toast.error(friendlyError(err, 'Rename failed.'))
    }
  }

  const submitDelete = async () => {
    if (!confirmDelete) return
    setDeleting(true)
    try {
      await documentsAPI.delete(confirmDelete.id)
      setDocs(list => list.filter(d => d.id !== confirmDelete.id))
      toast.success('Document deleted.')
      setConfirmDelete(null)
    } catch (err) {
      toast.error(friendlyError(err, 'Delete failed.'))
    } finally {
      setDeleting(false)
    }
  }

  /* ── Derived list ── */
  const q = query.trim().toLowerCase()
  const visible = docs
    .filter(d => (statusFilter === 'all' ? true : d.status === statusFilter))
    .filter(d => (q ? (d.original_filename || '').toLowerCase().includes(q) : true))
    .sort(SORTS[sortKey].fn)

  const counts = docs.reduce((acc, d) => {
    acc[d.status] = (acc[d.status] || 0) + 1
    return acc
  }, {})

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-2">
            <LoadingSkeleton className="h-7 w-40" />
            <LoadingSkeleton className="h-3 w-56" />
          </div>
          <LoadingSkeleton className="h-9 w-32 rounded-xl" />
        </div>
        <LoadingSkeleton className="h-44 w-full rounded-2xl" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <SkeletonDocCard key={i} />)}
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-4">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="page-title">Documents</h2>
          <p className="page-subtitle">
            {docs.length} document{docs.length !== 1 ? 's' : ''} in your workspace
            {counts.completed ? ` · ${counts.completed} ready to chat` : ''}
          </p>
        </div>
        <AnimatedButton variant="secondary" size="sm" onClick={() => fetchDocs()}>
          <RefreshCw size={14} /> Refresh
        </AnimatedButton>
      </div>

      {/* Upload */}
      <div>
        <DocumentUpload onUpload={handleUpload} uploading={uploading} progress={progress} phase={phase} />
        <AnimatePresence>
          {result && (
            <UploadResult ok={result.ok} errors={result.errors} onDismiss={() => setResult(null)} />
          )}
        </AnimatePresence>
      </div>

      {/* Filters — only worth showing once there's something to filter */}
      {docs.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1 sm:max-w-xs">
            <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              className="input-field py-2 pl-9 text-xs"
              placeholder="Search documents…"
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
          </div>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            aria-label="Filter by status"
            className="input-field w-auto py-2 text-xs"
          >
            <option value="all">All statuses</option>
            {Object.entries(STATUS_META).map(([key, m]) => (
              <option key={key} value={key}>{m.label}{counts[key] ? ` (${counts[key]})` : ''}</option>
            ))}
          </select>
          <select
            value={sortKey}
            onChange={e => setSortKey(e.target.value)}
            aria-label="Sort documents"
            className="input-field w-auto py-2 text-xs"
          >
            {Object.entries(SORTS).map(([key, s]) => <option key={key} value={key}>{s.label}</option>)}
          </select>
        </div>
      )}

      {/* Grid */}
      {docs.length === 0 ? (
        <div className="surface-gold">
          <EmptyState
            icon={BookOpen}
            title="Build Your Knowledge Base"
            description="Upload PDFs and start asking questions about your documents."
            actions={
              <>
                <AnimatedButton onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
                  <Upload size={14} /> Upload Document
                </AnimatedButton>
                <a href="https://research.ibm.com/blog/retrieval-augmented-generation-RAG" target="_blank" rel="noopener noreferrer">
                  <AnimatedButton variant="secondary">Learn How RAG Works</AnimatedButton>
                </a>
              </>
            }
          />
        </div>
      ) : visible.length === 0 ? (
        <EmptyState
          compact
          icon={Search}
          title="Nothing matches those filters"
          description="Try a different search term or clear the status filter."
          actions={
            <AnimatedButton variant="secondary" size="sm" onClick={() => { setQuery(''); setStatusFilter('all') }}>
              Clear filters
            </AnimatedButton>
          }
        />
      ) : (
        <motion.div
          layout
          initial="hidden"
          animate="show"
          variants={{ show: { transition: { staggerChildren: 0.045 } } }}
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          <AnimatePresence>
            {visible.map(doc => (
              <DocumentCard
                key={doc.id}
                doc={doc}
                variants={cardVariants}
                onView={openDetail}
                onChat={chatWithDoc}
                onRename={d => { setRenaming(d); setRenameValue(d.original_filename) }}
                onDelete={setConfirmDelete}
              />
            ))}
          </AnimatePresence>
        </motion.div>
      )}

      {/* ── Detail ── */}
      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail?.original_filename || ''} size="lg">
        {detail && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              {[
                { label: 'Type',   value: (detail.file_type || '').toUpperCase() },
                { label: 'Size',   value: detail.file_size_display },
                { label: 'Pages',  value: detail.page_count || '—' },
                { label: 'Chunks', value: detail.chunk_count || '—' },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-center">
                  <p className="font-display text-base font-bold text-white">{value}</p>
                  <p className="mt-0.5 text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
                </div>
              ))}
            </div>

            <div>
              <p className="label">AI summary</p>
              {summary === null ? (
                <div className="space-y-2">
                  <LoadingSkeleton className="h-3 w-full" />
                  <LoadingSkeleton className="h-3 w-11/12" />
                  <LoadingSkeleton className="h-3 w-4/5" />
                </div>
              ) : summary === '__error__' ? (
                <p className="text-sm text-zinc-500">The summary could not be loaded right now.</p>
              ) : (
                <p className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-xl border border-white/[0.06] bg-black/25 p-3.5 text-[13px] leading-relaxed text-zinc-300">
                  {summary || 'No summary is available for this document.'}
                </p>
              )}
            </div>

            {detail.status === 'completed' && (
              <div className="flex justify-end">
                <AnimatedButton size="sm" onClick={() => { setDetail(null); chatWithDoc(detail) }}>
                  Chat with this document
                </AnimatedButton>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* ── Rename ── */}
      <Modal open={!!renaming} onClose={() => setRenaming(null)} title="Rename document" size="sm">
        <div className="space-y-4">
          <div>
            <label className="label" htmlFor="doc-rename">Display name</label>
            <input
              id="doc-rename"
              autoFocus
              className="input-field"
              value={renameValue}
              onChange={e => setRenameValue(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') submitRename() }}
            />
            <p className="mt-1.5 text-[11px] text-zinc-600">
              Only the name changes — the file, its text and its embeddings stay exactly as they are.
            </p>
          </div>
          <div className="flex justify-end gap-2.5">
            <AnimatedButton variant="secondary" onClick={() => setRenaming(null)}>Cancel</AnimatedButton>
            <AnimatedButton onClick={submitRename} disabled={!renameValue.trim()}>Save</AnimatedButton>
          </div>
        </div>
      </Modal>

      {/* ── Delete ── */}
      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)} title="Delete document" size="sm">
        <div className="space-y-4">
          <p className="text-sm leading-relaxed text-zinc-400">
            Delete <span className="font-semibold text-zinc-200">“{confirmDelete?.original_filename}”</span>?
            Its file, extracted text and vector index are all removed, and chats grounded in it
            will no longer be able to cite it. This cannot be undone.
          </p>
          <div className="flex justify-end gap-2.5">
            <AnimatedButton variant="secondary" onClick={() => setConfirmDelete(null)}>Cancel</AnimatedButton>
            <AnimatedButton variant="danger" onClick={submitDelete} loading={deleting} disabled={deleting}>
              {!deleting && <Trash2 size={14} />} {deleting ? 'Deleting…' : 'Delete'}
            </AnimatedButton>
          </div>
        </div>
      </Modal>
    </div>
  )
}
