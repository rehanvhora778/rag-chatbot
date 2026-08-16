import { useRef, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Send, Paperclip, FileStack, Sparkles, Square, ShieldCheck, Loader2 } from 'lucide-react'

const SUGGESTIONS = [
  'Summarise the key points',
  'What are the main conclusions?',
  'List every recommendation',
  'Explain this in simple terms',
]

function IconButton({ icon: Icon, label, onClick, disabled, active, badge, busy }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      title={label}
      aria-label={label}
      className={`relative flex h-9 w-9 items-center justify-center rounded-xl border transition-colors disabled:opacity-40 ${
        active
          ? 'border-primary-500/45 bg-primary-500/15 text-primary-300'
          : 'border-primary-500/25 bg-primary-500/[0.04] text-primary-500/80 hover:border-primary-500/50 hover:bg-primary-500/[0.10] hover:text-primary-300'
      }`}
    >
      {busy
        ? <Loader2 size={15} className="animate-spin text-primary-300" />
        : <Icon size={15} />}
      {/* How many documents this chat is grounded in */}
      {badge > 0 && !busy && (
        <span className="absolute -right-1 -top-1 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-primary-500 px-1 text-[9px] font-bold text-ink-950">
          {badge}
        </span>
      )}
    </button>
  )
}

/**
 * Chat composer.
 *
 * Enter sends, Shift+Enter breaks the line, the textarea grows to a ceiling and
 * then scrolls, and the send button is inert while empty. The three icon
 * buttons are wired to real handlers passed by ChatPage — nothing here is
 * decorative.
 */
export default function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  onAttach,
  onPickDocuments,
  uploading = false,
  uploadPct = 0,
  docCount = 0,
  sending = false,
  disabled = false,
  placeholder = 'Ask a question about your documents...',
}) {
  const ref = useRef(null)
  const [showSuggestions, setShowSuggestions] = useState(false)

  // Grow with the content, up to ~6 lines.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`
  }, [value])

  const canSend = value.trim().length > 0 && !sending && !disabled

  const onKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (canSend) onSend()
    }
  }

  const applySuggestion = text => {
    onChange(text)
    setShowSuggestions(false)
    ref.current?.focus()
  }

  return (
    <div className="shrink-0 px-3 pb-3 pt-2 sm:px-5 sm:pb-4">
      <AnimatePresence>
        {showSuggestions && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.18 }}
            className="mb-2 flex flex-wrap gap-1.5"
          >
            {SUGGESTIONS.map(s => (
              <button
                key={s}
                onClick={() => applySuggestion(s)}
                className="rounded-full border border-primary-500/25 bg-primary-500/[0.07] px-3 py-1.5 text-[11px] font-medium text-primary-200 transition-colors hover:border-primary-500/50 hover:bg-primary-500/[0.14]"
              >
                {s}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {uploading && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="mb-2 flex items-center gap-2.5 rounded-xl border border-primary-500/25 bg-primary-500/[0.06] px-3 py-2">
              <Loader2 size={13} className="shrink-0 animate-spin text-primary-400" />
              <span className="shrink-0 text-[11.5px] text-zinc-300">
                Uploading <span className="tabular-nums text-primary-300">{uploadPct}%</span>
              </span>
              <span className="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                <motion.span
                  className="block h-full rounded-full bg-gradient-to-r from-primary-600 to-primary-300"
                  animate={{ width: `${uploadPct}%` }}
                  transition={{ ease: 'linear', duration: 0.2 }}
                />
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="rounded-2xl border border-primary-500/30 bg-ink-900/85 p-3 shadow-[0_0_28px_rgba(212,175,55,0.10)] backdrop-blur-xl transition-shadow duration-300 focus-within:border-primary-500/55 focus-within:shadow-[0_0_38px_rgba(212,175,55,0.20)]">
        <textarea
          ref={ref}
          rows={1}
          disabled={disabled}
          className="no-zoom-input w-full resize-none bg-transparent px-1 pb-2 pt-1 leading-relaxed text-zinc-100 placeholder-zinc-500 outline-none disabled:opacity-50"
          placeholder={placeholder}
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={onKeyDown}
        />

        <div className="flex items-center justify-between gap-2 pt-1">
          <div className="flex items-center gap-1.5">
            <IconButton
              icon={Paperclip}
              label={uploading ? `Uploading… ${uploadPct}%` : 'Upload a document (PDF, DOCX, TXT)'}
              onClick={onAttach}
              disabled={disabled}
              busy={uploading}
            />
            <IconButton
              icon={FileStack}
              label={docCount
                ? `Documents in this chat (${docCount}) — click to change`
                : 'Choose the documents this chat uses'}
              onClick={onPickDocuments}
              disabled={disabled}
              badge={docCount}
            />
            <IconButton
              icon={Sparkles}
              label="Suggested questions"
              onClick={() => setShowSuggestions(s => !s)}
              disabled={disabled}
              active={showSuggestions}
            />
          </div>

          {sending ? (
            <button
              onClick={onStop}
              title="Stop generating"
              aria-label="Stop generating"
              className="flex h-11 w-12 items-center justify-center rounded-xl border border-primary-500/35 bg-ink-800 text-primary-300 transition-colors hover:bg-ink-700"
            >
              <Square size={15} fill="currentColor" />
            </button>
          ) : (
            <motion.button
              onClick={onSend}
              disabled={!canSend}
              whileTap={canSend ? { scale: 0.94 } : undefined}
              title="Send"
              aria-label="Send message"
              className={`flex h-11 w-12 items-center justify-center rounded-xl transition-all duration-200 ${
                canSend
                  ? 'bg-gradient-to-b from-primary-300 via-primary-400 to-primary-600 text-ink-950 shadow-[0_0_20px_rgba(212,175,55,0.42)] hover:shadow-[0_0_30px_rgba(212,175,55,0.6)]'
                  : 'cursor-not-allowed border border-primary-500/20 bg-primary-500/[0.03] text-primary-500/40'
              }`}
            >
              <Send size={17} />
            </motion.button>
          )}
        </div>
      </div>

      <p className="mt-2.5 flex items-center justify-center gap-1.5 text-center text-[11px] text-zinc-600">
        <ShieldCheck size={12} className="shrink-0 text-primary-500/70" />
        RAG Chatbot may produce inaccurate information. Please verify important information.
      </p>
    </div>
  )
}
