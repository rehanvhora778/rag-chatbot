import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate, useSearchParams, useOutletContext, Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import axios from 'axios'
import {
  Plus, Trash2, Download, Search, X, MessageSquare, PanelRight,
  Pencil, FileText, BookOpen, Upload, Check, Menu, Sparkles,
} from 'lucide-react'
import toast from 'react-hot-toast'

import { chatAPI } from '../api/chat'
import { documentsAPI } from '../api/documents'
import Modal from '../components/common/Modal'
import AnimatedButton from '../components/ui/AnimatedButton'
import EmptyState from '../components/ui/EmptyState'
import LoadingSkeleton from '../components/ui/LoadingSkeleton'
import ChatMessage from '../components/chat/ChatMessage'
import ChatInput from '../components/chat/ChatInput'
import ChatHero from '../components/chat/ChatHero'
import ChatBackdrop from '../components/chat/ChatBackdrop'
import ChatRightPanel from '../components/chat/ChatRightPanel'
import TypingIndicator from '../components/chat/TypingIndicator'

/* Tell the sidebar its session list is stale. */
const notifySessionsChanged = () => window.dispatchEvent(new Event('chat-sessions-changed'))

/* Human-readable message for a failed request — never a raw stack or status. */
function friendlyError(err, fallback) {
  if (axios.isCancel?.(err) || err?.code === 'ERR_CANCELED') return null
  const status = err?.response?.status
  if (status === 429) return 'You are sending questions too quickly. Please wait a moment and try again.'
  if (status === 401) return 'Your session expired. Please sign in again.'
  if (status === 413) return 'That request was too large to process.'
  if (err?.code === 'ECONNABORTED') return 'The request timed out. The model may be busy — please try again.'
  if (!err?.response) return 'Cannot reach the server. Check your connection and try again.'
  return err.response?.data?.message || fallback
}

function SessionRow({ s, active, onOpen, onRename, onDelete }) {
  return (
    <div
      onClick={() => onOpen(s.id)}
      className={`row-gold group flex cursor-pointer items-center gap-2 px-3 py-2.5 ${
        active ? 'row-gold-active text-primary-100' : 'text-zinc-200'
      }`}
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium">{s.title}</p>
        <p className="mt-0.5 truncate text-[10px] text-zinc-600">
          {s.last_message_preview || `${s.message_count || 0} messages`}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
        <button
          onClick={e => { e.stopPropagation(); onRename(s) }}
          aria-label="Rename chat"
          className="flex h-6 w-6 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-primary-500/10 hover:text-primary-300"
        >
          <Pencil size={11} />
        </button>
        <button
          onClick={e => { e.stopPropagation(); onDelete(s) }}
          aria-label="Delete chat"
          className="flex h-6 w-6 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-red-500/10 hover:text-red-400"
        >
          <Trash2 size={11} />
        </button>
      </div>
    </div>
  )
}

export default function ChatPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { openMenu } = useOutletContext() ?? {}

  const [sessions, setSessions]   = useState([])
  const [current, setCurrent]     = useState(null)
  const [messages, setMessages]   = useState([])
  const [question, setQuestion]   = useState('')
  const [sending, setSending]     = useState(false)
  const [stage, setStage]         = useState(0)
  const [loading, setLoading]     = useState(false)
  const [exporting, setExporting] = useState(false)

  // Right panel data
  const [allDocs, setAllDocs]         = useState([])
  const [docsLoaded, setDocsLoaded]   = useState(false)
  const [config, setConfig]           = useState(null)

  // Panel visibility (drawer below its breakpoint)
  const [listOpen, setListOpen]   = useState(false)

  const [searchQ, setSearchQ] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)

  // Modals
  const [newChatOpen, setNewChatOpen] = useState(false)
  const [selectedDocs, setSelectedDocs] = useState([])
  const [chatTitle, setChatTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const [renaming, setRenaming] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null)

  // Composer: inline upload + "documents used by this chat"
  const [uploading, setUploading]   = useState(false)
  const [uploadPct, setUploadPct]   = useState(0)
  const [manageOpen, setManageOpen] = useState(false)
  const [manageDocs, setManageDocs] = useState([])
  const [savingDocs, setSavingDocs] = useState(false)

  const bottomRef   = useRef(null)
  const abortRef    = useRef(null)
  const fileRef     = useRef(null)   // hidden input behind the paperclip
  const pendingRef  = useRef([])     // ids uploaded here, watched until ready

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [])

  const loadSessions = useCallback(() => {
    chatAPI.listSessions({ page_size: 50 })
      .then(res => setSessions(res.data.data || []))
      .catch(() => toast.error('Could not load your chats.'))
  }, [])

  const loadDocs = useCallback(() => (
    documentsAPI.list({ page_size: 100 })
      .then(res => {
        const list = res.data.data || []
        setAllDocs(list)

        // Anything uploaded from the composer is watched until it finishes
        // processing, so the user is told when it's actually usable rather
        // than being left to guess.
        if (pendingRef.current.length) {
          const done = list.filter(
            d => pendingRef.current.includes(d.id) && d.status !== 'pending' && d.status !== 'processing',
          )
          if (done.length) {
            pendingRef.current = pendingRef.current.filter(id => !done.some(d => d.id === id))
            done.forEach(d => {
              if (d.status === 'completed') {
                toast.success(`“${d.original_filename}” is ready to chat with.`)
              } else {
                toast.error(`“${d.original_filename}” could not be processed. Try uploading it again.`)
              }
            })
          }
        }
        return list
      })
      .catch(() => { /* right panel is ambient */ })
      .finally(() => setDocsLoaded(true))
  ), [])

  useEffect(() => { loadSessions(); loadDocs() }, [loadSessions, loadDocs])

  /* Poll only while something is genuinely being processed. */
  const isBusy = allDocs.some(d => d.status === 'pending' || d.status === 'processing')
  useEffect(() => {
    if (!isBusy) return undefined
    const id = setInterval(loadDocs, 4000)
    return () => clearInterval(id)
  }, [isBusy, loadDocs])

  useEffect(() => {
    chatAPI.getConfig()
      .then(res => setConfig(res.data.data))
      .catch(() => { /* settings panel degrades to a skeleton */ })
  }, [])

  /* ── Load the open conversation ── */
  useEffect(() => {
    if (!sessionId) { setCurrent(null); setMessages([]); return }
    setLoading(true)
    chatAPI.getSession(sessionId)
      .then(res => {
        setCurrent(res.data.data.session)
        setMessages(res.data.data.messages || [])
      })
      .catch(err => {
        toast.error(friendlyError(err, 'That conversation could not be opened.'))
        navigate('/chat', { replace: true })
      })
      .finally(() => setLoading(false))
  }, [sessionId, navigate])

  useEffect(() => { scrollToBottom() }, [messages, scrollToBottom])

  /* ── Debounced chat search ── */
  useEffect(() => {
    if (!searchQ.trim()) { setSearchResults([]); return }
    const t = setTimeout(() => {
      setSearching(true)
      chatAPI.search({ q: searchQ, page_size: 20 })
        .then(res => setSearchResults(res.data.data || []))
        .catch(() => setSearchResults([]))
        .finally(() => setSearching(false))
    }, 350)
    return () => clearTimeout(t)
  }, [searchQ])

  /* ── Progress labels while a request is in flight ── */
  useEffect(() => {
    if (!sending) { setStage(0); return }
    const a = setTimeout(() => setStage(1), 1200)
    const b = setTimeout(() => setStage(2), 3200)
    return () => { clearTimeout(a); clearTimeout(b) }
  }, [sending])

  /* ── New chat ── */
  const openNewChat = useCallback(() => {
    setNewChatOpen(true)
    setSelectedDocs([])
    setChatTitle('')
    loadDocs()
  }, [loadDocs])

  useEffect(() => {
    if (searchParams.get('new') === '1') {
      openNewChat()
      searchParams.delete('new')
      setSearchParams(searchParams, { replace: true })
    }
  }, [searchParams, setSearchParams, openNewChat])

  const completedDocs = allDocs.filter(d => d.status === 'completed')

  /* ── Composer: paperclip → upload without leaving the conversation ── */
  const pickFiles = () => fileRef.current?.click()

  const handleComposerUpload = async e => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''            // let the same file be re-picked later
    if (!files.length) return

    const fd = new FormData()
    files.forEach(f => fd.append('files', f))

    setUploading(true)
    setUploadPct(0)
    const tId = toast.loading(`Uploading ${files.length} file${files.length > 1 ? 's' : ''}…`)

    try {
      const res = await documentsAPI.upload(fd, evt => {
        if (evt.total) setUploadPct(Math.round((evt.loaded / evt.total) * 100))
      })
      const uploaded = res.data.data?.uploaded || []
      const errors   = res.data.data?.errors   || []

      // Watch these until processing finishes (see loadDocs).
      pendingRef.current = [...pendingRef.current, ...uploaded.map(d => d.id)]

      if (uploaded.length) {
        toast.success(
          `${uploaded.length} file${uploaded.length > 1 ? 's' : ''} uploaded — processing now.`,
          { id: tId },
        )
      } else {
        toast.dismiss(tId)
      }
      errors.forEach(msg => toast.error(msg))
      loadDocs()
    } catch (err) {
      const errs = err.response?.data?.errors
      if (Array.isArray(errs) && errs.length) {
        toast.dismiss(tId)
        errs.forEach(msg => toast.error(msg))
      } else {
        toast.error(friendlyError(err, 'Upload failed. Please try again.'), { id: tId })
      }
    } finally {
      setUploading(false)
      setUploadPct(0)
    }
  }

  /* ── Composer: documents button → change what THIS chat is grounded in ── */
  const openManageDocs = () => {
    if (!sessionId) { openNewChat(); return }
    setManageDocs(current?.document_ids || [])
    setManageOpen(true)
    loadDocs()
  }

  const saveManagedDocs = async () => {
    if (!manageDocs.length) { toast.error('Select at least one document.'); return }
    setSavingDocs(true)
    try {
      const res = await chatAPI.updateSession(sessionId, { document_ids: manageDocs })
      setCurrent(res.data.data)
      setManageOpen(false)
      loadSessions()
      notifySessionsChanged()
      toast.success('Documents updated for this chat.')
    } catch (err) {
      toast.error(friendlyError(err, 'Could not update this chat’s documents.'))
    } finally {
      setSavingDocs(false)
    }
  }

  const createSession = async () => {
    if (!selectedDocs.length) { toast.error('Select at least one document to chat with.'); return }
    const title = chatTitle.trim() || (selectedDocs.length === 1
      ? completedDocs.find(d => d.id === selectedDocs[0])?.original_filename || 'New chat'
      : 'New chat')

    setCreating(true)
    try {
      const res = await chatAPI.createSession({ title, document_ids: selectedDocs })
      setNewChatOpen(false)
      loadSessions()
      notifySessionsChanged()
      navigate(`/chat/${res.data.data.id}`)
    } catch (err) {
      toast.error(friendlyError(err, 'Could not start that chat.'))
    } finally {
      setCreating(false)
    }
  }

  const sendMessage = async () => {
    const q = question.trim()
    if (!q || sending || !sessionId) return

    setQuestion('')
    setSending(true)
    setMessages(m => [...m, { role: 'user', content: q, created_at: new Date().toISOString(), sources: [] }])

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await chatAPI.sendMessage(sessionId, { question: q }, { signal: controller.signal })
      const { answer, citations } = res.data.data
      setMessages(m => [...m, {
        role: 'assistant',
        content: answer,
        sources: citations || [],
        created_at: new Date().toISOString(),
        _animate: true,
      }])
      loadSessions()
      notifySessionsChanged()
    } catch (err) {
      const msg = friendlyError(err, 'The assistant could not answer that. Please try again.')
      if (msg) {
        toast.error(msg)
        // Drop the optimistic question so the transcript doesn't show an
        // unanswered message the server never stored.
        setMessages(m => m.slice(0, -1))
      } else {
        // Cancelled by the user — the pipeline may still have persisted the
        // exchange, so reload rather than guess.
        chatAPI.getSession(sessionId)
          .then(r => setMessages(r.data.data.messages || []))
          .catch(() => setMessages(m => m.slice(0, -1)))
      }
    } finally {
      abortRef.current = null
      setSending(false)
    }
  }

  const stopGenerating = () => {
    abortRef.current?.abort()
    toast('Generation stopped.', { icon: '⏹' })
  }

  const submitRename = async () => {
    const title = renameValue.trim()
    if (!title || !renaming) return
    try {
      await chatAPI.updateSession(renaming.id, { title })
      toast.success('Chat renamed.')
      setRenaming(null)
      loadSessions()
      notifySessionsChanged()
      if (renaming.id === sessionId) setCurrent(c => (c ? { ...c, title } : c))
    } catch (err) {
      toast.error(friendlyError(err, 'Rename failed.'))
    }
  }

  const submitDelete = async () => {
    if (!confirmDelete) return
    const id = confirmDelete.id
    try {
      await chatAPI.deleteSession(id)
      toast.success('Chat deleted.')
      setConfirmDelete(null)
      setSessions(list => list.filter(s => s.id !== id))
      notifySessionsChanged()
      if (sessionId === id) navigate('/chat')
    } catch (err) {
      toast.error(friendlyError(err, 'Delete failed.'))
    }
  }

  /* ── PDF export: a high-resolution print of the rendered cards ── */
  const PAGE_BG = '#050506'

  const exportFilename = () => {
    const slug = s => (s || 'document').replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').slice(0, 60) || 'document'
    const idxs = messages.map((m, i) => (m.role === 'assistant' ? i : -1)).filter(i => i >= 0)
    if (idxs.length === 1) {
      const q = idxs[0] > 0 ? messages[idxs[0] - 1]?.content : ''
      return `${slug(q || current?.title)}.pdf`
    }
    return `${slug(current?.title)}.pdf`
  }

  const exportPDF = async () => {
    if (exporting) return

    const bubbles = Array.from(document.querySelectorAll('[data-msg-bubble]'))
    const exchanges = []
    let pendingQ = null
    for (const el of bubbles) {
      if (el.dataset.role === 'user') pendingQ = el
      else { exchanges.push({ q: pendingQ, a: el }); pendingQ = null }
    }
    if (!exchanges.length) { toast.error('There is no answer to export yet.'); return }

    setExporting(true)
    const tId = toast.loading('Generating PDF…')
    try {
      const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
        import('html2canvas'),
        import('jspdf'),
      ])
      if (document.fonts?.ready) await document.fonts.ready

      const SCALE = 3
      const pdf = new jsPDF({ unit: 'pt', format: 'a4', compress: true })
      const pageW = pdf.internal.pageSize.getWidth()
      const pageH = pdf.internal.pageSize.getHeight()
      const margin = 28
      const contentW = pageW - margin * 2

      const fillBg = () => { pdf.setFillColor(5, 5, 6); pdf.rect(0, 0, pageW, pageH, 'F') }
      const capture = el => html2canvas(el, {
        scale: SCALE,
        backgroundColor: PAGE_BG,
        useCORS: true,
        letterRendering: true,
        logging: false,
        ignoreElements: e => e.classList?.contains?.('export-hide'),
      })

      /* Blocks a page break must not land inside, as [top, bottom] offsets in
         canvas pixels. The Sources panel is one: slicing through it splits the
         citation cards in half and leaves the page numbers unreadable. */
      const keepWhole = el => {
        const base = el.getBoundingClientRect().top
        return Array.from(el.querySelectorAll('[data-sources]')).map(node => {
          const r = node.getBoundingClientRect()
          return [(r.top - base) * SCALE, (r.bottom - base) * SCALE]
        })
      }

      const placeSliced = (canvas, x, targetW, startY, avoid = []) => {
        const pxPerPt = canvas.width / targetW
        let srcY = 0
        let y = startY
        while (srcY < canvas.height) {
          let availPx = Math.floor(((pageH - margin) - y) * pxPerPt)
          if (availPx < 1) { pdf.addPage(); fillBg(); y = margin; availPx = Math.floor(((pageH - margin) - y) * pxPerPt) }
          let h = Math.min(availPx, canvas.height - srcY)

          // If this page would end inside a keep-whole block, stop just above it
          // so the block travels to the next page intact. Skipped when the block
          // is taller than a full page (it has to be split then) or when pulling
          // back would leave nothing to draw.
          const cut = srcY + h
          for (const [top, bottom] of avoid) {
            const pageCapacityPx = ((pageH - margin * 2)) * pxPerPt
            if (cut > top && cut < bottom && bottom - top <= pageCapacityPx && top > srcY) {
              h = top - srcY
              break
            }
          }

          const slice = document.createElement('canvas')
          slice.width = canvas.width
          slice.height = h
          const ctx = slice.getContext('2d')
          ctx.fillStyle = PAGE_BG
          ctx.fillRect(0, 0, slice.width, slice.height)
          ctx.drawImage(canvas, 0, srcY, canvas.width, h, 0, 0, canvas.width, h)
          pdf.addImage(slice.toDataURL('image/png'), 'PNG', x, y, targetW, h / pxPerPt)
          srcY += h
          y += h / pxPerPt
          if (srcY < canvas.height) { pdf.addPage(); fillBg(); y = margin }
        }
        return y
      }

      let firstPage = true
      for (const ex of exchanges) {
        if (!firstPage) pdf.addPage()
        firstPage = false
        fillBg()
        let y = margin

        if (ex.q) {
          const qc = await capture(ex.q)
          const naturalWpt = (qc.width / SCALE) * 0.75
          const qW = Math.min(contentW * 0.72, naturalWpt)
          const qX = pageW - margin - qW
          y = placeSliced(qc, qX, qW, y) + 16
        }

        const avoid = keepWhole(ex.a)
        const ac = await capture(ex.a)
        if ((pageH - margin) - y < 130) { pdf.addPage(); fillBg(); y = margin }
        placeSliced(ac, margin, contentW, y, avoid)
      }

      pdf.save(exportFilename())
      toast.success('PDF downloaded.', { id: tId })
    } catch (err) {
      console.error('PDF export failed:', err)
      toast.error('Export failed. Please try again.', { id: tId })
    } finally {
      setExporting(false)
    }
  }

  const openSession = id => { setListOpen(false); navigate(`/chat/${id}`) }

  const shownSessions = searchQ.trim() ? searchResults : sessions

  /* ── Session list, shared by the desktop column and the mobile drawer ── */
  const sessionList = (
    <>
      <div className="shrink-0 space-y-2 border-b border-primary-500/20 p-3">
        <AnimatedButton onClick={openNewChat} className="w-full">
          <Plus size={14} /> New Chat
        </AnimatedButton>
        <div className="relative">
          <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            className="input-field py-2 pl-9 pr-8 text-xs"
            placeholder="Search chats…"
            value={searchQ}
            onChange={e => setSearchQ(e.target.value)}
          />
          {searchQ && (
            <button
              onClick={() => setSearchQ('')}
              aria-label="Clear search"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2.5">
        {searchQ && searching ? (
          <div className="space-y-2">
            {[0, 1, 2].map(i => <LoadingSkeleton key={i} className="h-12 w-full rounded-xl" />)}
          </div>
        ) : shownSessions.length === 0 ? (
          <p className="px-3 py-10 text-center text-xs leading-relaxed text-zinc-600">
            {searchQ ? `No chats match “${searchQ}”.` : 'No conversations yet.'}
          </p>
        ) : (
          shownSessions.map(s => (
            <SessionRow
              key={s.id}
              s={s}
              active={sessionId === s.id}
              onOpen={openSession}
              onRename={x => { setRenaming(x); setRenameValue(x.title) }}
              onDelete={setConfirmDelete}
            />
          ))
        )}
      </div>
    </>
  )

  // Rendered in two places (docked rail + drawer); only the docked one carries
  // the ref that the header's "Engine" button scrolls to.
  const renderRightPanel = () => (
    <ChatRightPanel
      documents={allDocs}
      loading={!docsLoaded}
      config={config}
      onAddDocument={pickFiles}
    />
  )

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      {/* ── Full chat manager (search / rename / delete).
             Always a drawer: the workspace is a three-column layout, and the
             sidebar's Recent Chats covers everyday switching. ── */}
      <AnimatePresence>
        {listOpen && (
          <div className="fixed inset-0 z-40">
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setListOpen(false)}
              className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            />
            <motion.aside
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'spring', stiffness: 380, damping: 38 }}
              className="absolute inset-y-0 right-0 flex w-[min(86vw,320px)] flex-col border-l border-primary-500/15 bg-ink-900"
            >
              <div className="flex h-14 shrink-0 items-center justify-between border-b border-primary-500/20 px-4">
                <p className="font-display text-sm font-semibold text-white">Your chats</p>
                <button onClick={() => setListOpen(false)} aria-label="Close" className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 hover:bg-white/5 hover:text-white">
                  <X size={16} />
                </button>
              </div>
              {sessionList}
            </motion.aside>
          </div>
        )}
      </AnimatePresence>

      {/* ── Centre column ── */}
      <div className="panel-gold relative flex min-w-0 flex-1 flex-col overflow-hidden">
        <ChatBackdrop />

        {/* Header */}
        <div className="relative z-10 flex shrink-0 items-start gap-2 px-3 pb-3 pt-4 sm:px-5 sm:pt-5">
          <button
            onClick={openMenu}
            aria-label="Open menu"
            className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-zinc-400 transition-colors hover:bg-primary-500/10 hover:text-primary-300 lg:hidden"
          >
            <Menu size={19} />
          </button>

          <div className="min-w-0 flex-1">
            <h1 className="truncate font-display text-xl font-bold tracking-tight text-white sm:text-[26px]">
              RAG Chatbot
            </h1>
            <p className="mt-0.5 truncate text-[12.5px] text-zinc-500">
              {sessionId && current
                ? `${current.title}${current.document_names?.length ? ` · ${current.document_names.join(', ')}` : ''}`
                : 'Ask anything about your documents'}
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            {sessionId && (
              <>
                <button
                  onClick={() => { setRenaming(current); setRenameValue(current?.title || '') }}
                  disabled={!current}
                  aria-label="Rename this chat"
                  title="Rename chat"
                  className="hidden h-9 w-9 items-center justify-center rounded-xl border border-primary-500/25 bg-primary-500/[0.04] text-zinc-400 transition-colors hover:border-primary-500/30 hover:text-primary-300 disabled:opacity-40 sm:flex"
                >
                  <Pencil size={15} />
                </button>
                <button
                  onClick={exportPDF}
                  disabled={exporting || !messages.length}
                  aria-label="Export as PDF"
                  title="Export as PDF"
                  className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary-500/25 bg-primary-500/[0.04] text-zinc-400 transition-colors hover:border-primary-500/30 hover:text-primary-300 disabled:opacity-40"
                >
                  {exporting
                    ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary-500/40 border-t-primary-400" />
                    : <Download size={15} />}
                </button>
              </>
            )}
            <button
              onClick={() => setListOpen(true)}
              aria-label="Show all chats"
              title="All chats"
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary-500/25 bg-primary-500/[0.04] text-zinc-400 transition-colors hover:border-primary-500/30 hover:text-primary-300"
            >
              <PanelRight size={15} />
            </button>
          </div>
        </div>

        {/* Transcript */}
        <div className="relative z-10 min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 pb-2 sm:px-5">
          <div className="mx-auto w-full max-w-3xl">
            {!sessionId ? (
              <>
                <ChatHero />
                <EmptyState
                  icon={Sparkles}
                  title="Start a conversation"
                  description="Pick the documents you want to ask about, and every answer will come back with the pages it was drawn from."
                  actions={
                    <>
                      <AnimatedButton onClick={openNewChat}><Plus size={15} /> New Chat</AnimatedButton>
                      <Link to="/documents"><AnimatedButton variant="secondary"><Upload size={14} /> Upload a document</AnimatedButton></Link>
                    </>
                  }
                />
                {sessions.length > 0 && (
                  <div className="mb-4">
                    <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-zinc-600">
                      Continue where you left off
                    </p>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {sessions.slice(0, 4).map(s => (
                        <button
                          key={s.id}
                          onClick={() => openSession(s.id)}
                          className="group flex items-center gap-3 rounded-xl border border-primary-500/[0.22] bg-ink-900/70 p-3 text-left backdrop-blur-sm transition-all hover:-translate-y-0.5 hover:border-primary-500/35 hover:bg-primary-500/[0.05]"
                        >
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-500/10 ring-1 ring-primary-500/20">
                            <MessageSquare size={14} className="text-primary-400" />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[13px] font-medium text-zinc-200 group-hover:text-primary-100">{s.title}</span>
                            <span className="mt-0.5 block truncate text-[10px] text-zinc-600">
                              {s.last_message_preview || `${s.message_count || 0} messages`}
                            </span>
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : loading ? (
              <div className="space-y-5 pt-3">
                <LoadingSkeleton className="ml-auto h-14 w-2/3 rounded-2xl" />
                <LoadingSkeleton className="h-32 w-full rounded-2xl" />
                <LoadingSkeleton className="ml-auto h-14 w-1/2 rounded-2xl" />
              </div>
            ) : (
              <>
                {messages.length === 0 && (
                  <EmptyState
                    icon={MessageSquare}
                    compact
                    title="Ask your first question"
                    description={`This chat is grounded in ${current?.document_names?.join(', ') || 'your documents'}. Answers will cite the pages they came from.`}
                  />
                )}
                {messages.map((msg, i) => (
                  <ChatMessage key={msg.id || i} msg={msg} scrollToBottom={scrollToBottom} />
                ))}
                <AnimatePresence>{sending && <TypingIndicator stage={stage} />}</AnimatePresence>
              </>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* Composer */}
        <div className="relative z-10 mx-auto w-full max-w-3xl">
          <ChatInput
            value={question}
            onChange={setQuestion}
            onSend={sendMessage}
            onStop={stopGenerating}
            onAttach={pickFiles}
            onPickDocuments={openManageDocs}
            uploading={uploading}
            uploadPct={uploadPct}
            docCount={current?.document_ids?.length || 0}
            sending={sending}
            disabled={loading || !sessionId}
            placeholder={sessionId ? 'Ask a question about your documents...' : 'Start a new chat to ask a question…'}
          />

          {/* Behind the paperclip. Same types the backend accepts. */}
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".pdf,.docx,.txt"
            onChange={handleComposerUpload}
            className="hidden"
          />
        </div>
      </div>

      {/* ── Right rail (xl and up) ── */}
      <aside className="hidden w-[340px] shrink-0 overflow-hidden xl:block">
        {renderRightPanel()}
      </aside>

      {/* ── New chat ── */}
      <Modal open={newChatOpen} onClose={() => setNewChatOpen(false)} title="New chat" size="md">
        <div className="space-y-4">
          <div>
            <label className="label" htmlFor="chat-title">Title <span className="normal-case text-zinc-600">(optional)</span></label>
            <input
              id="chat-title"
              className="input-field"
              placeholder="e.g. Research paper analysis"
              value={chatTitle}
              onChange={e => setChatTitle(e.target.value)}
            />
          </div>

          <div>
            <label className="label">Documents to chat with — {selectedDocs.length} selected</label>
            {!docsLoaded ? (
              <div className="space-y-2 rounded-xl border border-white/10 p-3">
                {[0, 1, 2].map(i => <LoadingSkeleton key={i} className="h-9 w-full rounded-lg" />)}
              </div>
            ) : completedDocs.length === 0 ? (
              <EmptyState
                compact
                icon={BookOpen}
                title="Build Your Knowledge Base"
                description="Upload PDFs and start asking questions about your documents."
                actions={
                  <Link to="/documents" onClick={() => setNewChatOpen(false)}>
                    <AnimatedButton size="sm"><Upload size={13} /> Upload Document</AnimatedButton>
                  </Link>
                }
                className="border border-dashed border-primary-500/20"
              />
            ) : (
              <>
                <div className="max-h-56 overflow-y-auto rounded-xl border border-white/10">
                  {completedDocs.map(d => {
                    const checked = selectedDocs.includes(d.id)
                    return (
                      <label
                        key={d.id}
                        className={`flex cursor-pointer items-center gap-3 border-b border-primary-500/15 px-3.5 py-2.5 transition-colors last:border-0 ${
                          checked ? 'bg-primary-500/[0.08]' : 'hover:bg-white/[0.03]'
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="sr-only"
                          checked={checked}
                          onChange={e => setSelectedDocs(prev =>
                            e.target.checked ? [...prev, d.id] : prev.filter(id => id !== d.id))}
                        />
                        <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                          checked ? 'border-primary-500 bg-primary-500 text-ink-950' : 'border-white/20'
                        }`}>
                          {checked && <Check size={11} strokeWidth={3.5} />}
                        </span>
                        <FileText size={13} className="shrink-0 text-zinc-500" />
                        <span className="min-w-0 flex-1 truncate text-[13px] text-zinc-300">{d.original_filename}</span>
                        <span className="shrink-0 text-[10px] uppercase text-zinc-600">{d.file_type}</span>
                      </label>
                    )
                  })}
                </div>
                <button
                  onClick={() => setSelectedDocs(
                    selectedDocs.length === completedDocs.length ? [] : completedDocs.map(d => d.id),
                  )}
                  className="mt-2 text-[11px] font-semibold text-primary-400 hover:text-primary-300"
                >
                  {selectedDocs.length === completedDocs.length ? 'Clear selection' : 'Select all documents'}
                </button>
              </>
            )}
          </div>

          {completedDocs.length > 0 && (
            <div className="flex justify-end gap-2.5 pt-1">
              <AnimatedButton variant="secondary" onClick={() => setNewChatOpen(false)}>Cancel</AnimatedButton>
              <AnimatedButton onClick={createSession} loading={creating} disabled={creating || !selectedDocs.length}>
                {creating ? 'Creating…' : 'Start chat'}
              </AnimatedButton>
            </div>
          )}
        </div>
      </Modal>

      {/* ── Documents used by THIS chat ── */}
      <Modal open={manageOpen} onClose={() => setManageOpen(false)} title="Documents in this chat" size="md">
        <div className="space-y-4">
          <p className="text-[12.5px] leading-relaxed text-zinc-500">
            Answers in this conversation are grounded only in the documents ticked below.
            Changing them affects your next question — earlier answers keep the sources they
            were written from.
          </p>

          {!docsLoaded ? (
            <div className="space-y-2 rounded-xl border border-primary-500/20 p-3">
              {[0, 1, 2].map(i => <LoadingSkeleton key={i} className="h-9 w-full rounded-lg" />)}
            </div>
          ) : completedDocs.length === 0 ? (
            <EmptyState
              compact
              icon={BookOpen}
              title="No documents ready yet"
              description="Upload a file and it will appear here once processing finishes."
              actions={
                <AnimatedButton size="sm" onClick={() => { setManageOpen(false); pickFiles() }}>
                  <Upload size={13} /> Upload a document
                </AnimatedButton>
              }
              className="border border-dashed border-primary-500/25"
            />
          ) : (
            <>
              <div className="max-h-56 overflow-y-auto rounded-xl border border-primary-500/20">
                {completedDocs.map(d => {
                  const checked = manageDocs.includes(d.id)
                  return (
                    <label
                      key={d.id}
                      className={`flex cursor-pointer items-center gap-3 border-b border-primary-500/15 px-3.5 py-2.5 transition-colors last:border-0 ${
                        checked ? 'bg-primary-500/[0.08]' : 'hover:bg-primary-500/[0.04]'
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={checked}
                        onChange={e => setManageDocs(prev =>
                          e.target.checked ? [...prev, d.id] : prev.filter(id => id !== d.id))}
                      />
                      <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                        checked ? 'border-primary-500 bg-primary-500 text-ink-950' : 'border-primary-500/40'
                      }`}>
                        {checked && <Check size={11} strokeWidth={3.5} />}
                      </span>
                      <FileText size={13} className="shrink-0 text-primary-500/70" />
                      <span className="min-w-0 flex-1 truncate text-[13px] text-zinc-300">{d.original_filename}</span>
                      <span className="shrink-0 text-[10px] uppercase text-zinc-600">{d.file_type}</span>
                    </label>
                  )
                })}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2">
                <button
                  onClick={() => { setManageOpen(false); pickFiles() }}
                  className="inline-flex items-center gap-1.5 text-[11.5px] font-semibold text-primary-400 hover:text-primary-300"
                >
                  <Upload size={12} /> Upload another
                </button>
                <span className="text-[11px] text-zinc-600">{manageDocs.length} selected</span>
              </div>

              <div className="flex justify-end gap-2.5 pt-1">
                <AnimatedButton variant="secondary" onClick={() => setManageOpen(false)}>Cancel</AnimatedButton>
                <AnimatedButton
                  onClick={saveManagedDocs}
                  loading={savingDocs}
                  disabled={savingDocs || !manageDocs.length}
                >
                  {savingDocs ? 'Saving…' : 'Save'}
                </AnimatedButton>
              </div>
            </>
          )}
        </div>
      </Modal>

      {/* ── Rename ── */}
      <Modal open={!!renaming} onClose={() => setRenaming(null)} title="Rename chat" size="sm">
        <div className="space-y-4">
          <div>
            <label className="label" htmlFor="rename-input">Title</label>
            <input
              id="rename-input"
              autoFocus
              className="input-field"
              value={renameValue}
              onChange={e => setRenameValue(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') submitRename() }}
            />
          </div>
          <div className="flex justify-end gap-2.5">
            <AnimatedButton variant="secondary" onClick={() => setRenaming(null)}>Cancel</AnimatedButton>
            <AnimatedButton onClick={submitRename} disabled={!renameValue.trim()}>Save</AnimatedButton>
          </div>
        </div>
      </Modal>

      {/* ── Delete confirmation ── */}
      <Modal open={!!confirmDelete} onClose={() => setConfirmDelete(null)} title="Delete chat" size="sm">
        <div className="space-y-4">
          <p className="text-sm leading-relaxed text-zinc-400">
            Delete <span className="font-semibold text-zinc-200">“{confirmDelete?.title}”</span> and all of its
            messages? Your documents are not affected. This cannot be undone.
          </p>
          <div className="flex justify-end gap-2.5">
            <AnimatedButton variant="secondary" onClick={() => setConfirmDelete(null)}>Cancel</AnimatedButton>
            <AnimatedButton variant="danger" onClick={submitDelete}><Trash2 size={14} /> Delete</AnimatedButton>
          </div>
        </div>
      </Modal>
    </div>
  )
}
