import { useState, useEffect, memo } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { User, Copy, Check, ThumbsUp, ThumbsDown } from 'lucide-react'
import toast from 'react-hot-toast'
import { chatAPI } from '../../api/chat'
import Logo from '../ui/Logo'
import MarkdownRenderer from './MarkdownRenderer'
import SourcesPanel from './SourcesPanel'

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard unavailable (insecure context / denied) */ }
  }
  return (
    <button
      onClick={copy}
      aria-label="Copy answer"
      className="export-hide inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium text-zinc-500 transition-colors hover:bg-primary-500/10 hover:text-primary-300"
    >
      <AnimatePresence mode="wait" initial={false}>
        {copied ? (
          <motion.span key="c" initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-1 text-success-400">
            <Check size={11} /> Copied
          </motion.span>
        ) : (
          <motion.span key="d" initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center gap-1">
            <Copy size={11} /> Copy
          </motion.span>
        )}
      </AnimatePresence>
    </button>
  )
}

function UserAvatar() {
  return (
    <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-primary-500/40 bg-ink-800 shadow-[0_0_14px_rgba(212,175,55,0.18)]">
      <User size={15} className="text-primary-400" />
    </div>
  )
}

/**
 * Types an already-complete answer out character by character.
 *
 * Used for answers that arrive whole — the non-streaming /message/ endpoint,
 * still used as a fallback — never for a live stream. Simulating a typing pace
 * on top of real tokens would make the answer lag behind what the server has
 * already sent, so streamed messages render exactly what has arrived.
 */
function StreamingMarkdown({ content, onTick }) {
  const [shown, setShown] = useState('')

  useEffect(() => {
    let i = 0
    const step = Math.max(3, Math.ceil(content.length / 250))
    const id = setInterval(() => {
      i += step
      setShown(content.slice(0, i))
      onTick?.()
      if (i >= content.length) { setShown(content); clearInterval(id) }
    }, 16)
    return () => clearInterval(id)
  }, [content, onTick])

  const done = shown.length >= content.length
  return (
    <div className="relative">
      <MarkdownRenderer content={shown} />
      {!done && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-blink rounded-sm bg-primary-400 align-middle" />}
    </div>
  )
}

/* Why an answer was unhelpful. Only shown after a thumbs-down, because every
   option describes a way the answer was wrong — asking after a thumbs-up would
   be asking the user to invent a complaint. */
const REASONS = [
  ['incorrect',     'Incorrect'],
  ['irrelevant',    'Irrelevant sources'],
  ['missing',       'Missing information'],
  ['hallucination', 'Made something up'],
  ['other',         'Other'],
]

function FeedbackButtons({ messageId }) {
  const [rating, setRating] = useState(null)
  const [askReason, setAskReason] = useState(false)
  const [saving, setSaving] = useState(false)

  // Whatever verdict already exists, so reopening a conversation shows the
  // rating the user gave rather than a blank pair of buttons.
  useEffect(() => {
    let live = true
    chatAPI.getFeedback(messageId)
      .then(res => { if (live && res.data.data) setRating(res.data.data.rating) })
      .catch(() => { /* absent feedback is the normal case, not an error */ })
    return () => { live = false }
  }, [messageId])

  const send = async (value, reason = '') => {
    if (saving) return
    setSaving(true)
    // Optimistic: the button responds immediately and is reverted only if the
    // request actually fails.
    const previous = rating
    setRating(value)
    try {
      await chatAPI.feedback(messageId, { rating: value, reason })
      if (value === -1 && !reason) setAskReason(true)
      else setAskReason(false)
    } catch {
      setRating(previous)
      toast.error('Could not save that feedback.')
    } finally {
      setSaving(false)
    }
  }

  const buttonClass = (active, tone) =>
    `export-hide inline-flex items-center rounded-md p-1 transition-colors ${
      active ? tone : 'text-zinc-500 hover:bg-primary-500/10 hover:text-primary-300'
    }`

  return (
    <div className="flex items-center gap-0.5">
      <button
        onClick={() => send(1)}
        aria-label="Helpful"
        aria-pressed={rating === 1}
        className={buttonClass(rating === 1, 'bg-success-500/15 text-success-400')}
      >
        <ThumbsUp size={11} />
      </button>
      <button
        onClick={() => send(-1)}
        aria-label="Not helpful"
        aria-pressed={rating === -1}
        className={buttonClass(rating === -1, 'bg-red-500/15 text-red-400')}
      >
        <ThumbsDown size={11} />
      </button>

      <AnimatePresence>
        {askReason && (
          <motion.div
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            className="export-hide ml-1 flex flex-wrap items-center gap-1"
          >
            {REASONS.map(([value, label]) => (
              <button
                key={value}
                onClick={() => send(-1, value)}
                className="rounded-full border border-primary-500/25 px-2 py-0.5 text-[10px] text-zinc-400 transition-colors hover:border-primary-400/50 hover:text-primary-200"
              >
                {label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}


function ChatMessage({ msg, scrollToBottom }) {
  const isUser = msg.role === 'user'
  const sources = msg.sources || []

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
        className="mb-6 flex flex-row-reverse items-start gap-3"
      >
        <UserAvatar />
        <div className="flex min-w-0 max-w-[86%] flex-col items-end gap-1 sm:max-w-[78%]">
          <div
            data-msg-bubble=""
            data-role="user"
            className="rounded-2xl border border-primary-500/45 bg-ink-900/85 px-5 py-3 text-[14px] leading-relaxed text-zinc-100 shadow-[0_0_22px_rgba(212,175,55,0.16)] backdrop-blur-sm"
          >
            <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{msg.content}</p>
          </div>
          <span className="px-1 text-[10px] text-zinc-600">
            {msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
          </span>
        </div>
      </motion.div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="mb-6 flex items-start gap-3"
    >
      <Logo size={38} id="msg" className="mt-0.5" />

      <div className="flex w-full min-w-0 flex-col items-start gap-1">
        <div
          data-msg-bubble=""
          data-role="assistant"
          className="w-full min-w-0 rounded-2xl border border-primary-500/40 bg-ink-900/80 px-4 py-4 text-[14px] leading-relaxed shadow-[0_0_26px_rgba(212,175,55,0.10),0_8px_34px_rgba(0,0,0,0.5)] backdrop-blur-md sm:px-5"
        >
          {/* Three cases, in order of how the text arrives:
              _streaming — tokens are landing now, so render exactly what has
                           arrived plus a caret. No simulated typing: the real
                           pace is the model's, and faking it on top would make
                           the answer lag behind what the server already sent.
              _animate   — a completed answer being replayed for effect.
              otherwise  — history, rendered immediately. */}
          {msg._streaming ? (
            <div className="relative">
              <MarkdownRenderer content={msg.content} />
              <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-blink rounded-sm bg-primary-400 align-middle" />
            </div>
          ) : msg._animate ? (
            <StreamingMarkdown content={msg.content} onTick={scrollToBottom} />
          ) : (
            <MarkdownRenderer content={msg.content} />
          )}

          {/* Citations. Streamed ahead of the first token, so Sources appear
              while the answer is still being written rather than making the
              layout jump when they arrive at the end. */}
          <SourcesPanel sources={sources} />
        </div>

        <div className="flex items-center gap-1 px-1">
          <CopyButton text={msg.content} />
          {/* Only once the turn is saved: feedback attaches to a stored
              message, and until `done` arrives there is no id to attach to. */}
          {msg.id && !msg._streaming && <FeedbackButtons messageId={msg.id} />}
          <span className="text-[10px] text-zinc-600">
            {msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
          </span>
        </div>
      </div>
    </motion.div>
  )
}

export default memo(ChatMessage)
