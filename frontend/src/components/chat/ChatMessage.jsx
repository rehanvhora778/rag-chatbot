import { useState, useEffect, memo } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { User, Copy, Check } from 'lucide-react'
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
 * The chat API returns the full response in one shot (it is not a streaming
 * endpoint), so this is presentation only — it never changes what is shown, and
 * the text is always complete in the DOM by the time the caret disappears.
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
          {msg._animate
            ? <StreamingMarkdown content={msg.content} onTick={scrollToBottom} />
            : <MarkdownRenderer content={msg.content} />}

          {/* Citations. The API returns these on every grounded answer — an
              answer with no qualifying context correctly has none. */}
          <SourcesPanel sources={sources} />
        </div>

        <div className="flex items-center gap-1 px-1">
          <CopyButton text={msg.content} />
          <span className="text-[10px] text-zinc-600">
            {msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
          </span>
        </div>
      </div>
    </motion.div>
  )
}

export default memo(ChatMessage)
