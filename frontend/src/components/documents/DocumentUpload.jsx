import { useState, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CloudUpload, CheckCircle2, AlertTriangle, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'

const ACCEPT = '.pdf,.docx,.txt'

/**
 * Drag-and-drop upload zone.
 *
 * The progress bar tracks the *transfer* only — that is the one number the
 * browser genuinely knows (axios `onUploadProgress`). Once the bytes are on the
 * server, processing happens in a background thread that exposes no progress,
 * so the UI switches to an indeterminate "processing" state and the document
 * card takes over reporting status. No fabricated percentages.
 */
export default function DocumentUpload({ onUpload, uploading, progress, phase }) {
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef(null)

  const openPicker = () => fileRef.current?.click()

  const handleFiles = files => {
    const list = Array.from(files || [])
    if (list.length) onUpload(list)
    if (fileRef.current) fileRef.current.value = ''
  }

  const onDrop = e => {
    e.preventDefault()
    setDragOver(false)
    handleFiles(e.dataTransfer.files)
  }

  return (
    <div>
      <motion.div
        role="button"
        tabIndex={0}
        onClick={openPicker}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openPicker() } }}
        onDrop={onDrop}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        animate={{ scale: dragOver ? 1.008 : 1 }}
        className={cn(
          'relative cursor-pointer overflow-hidden rounded-2xl border-2 border-dashed p-6 text-center transition-colors sm:p-10',
          'focus:outline-none focus-visible:border-primary-500/70',
          dragOver ? 'border-primary-500/70 bg-primary-500/[0.07]' : 'border-primary-500/20 hover:border-primary-500/45 hover:bg-primary-500/[0.03]',
        )}
      >
        {(dragOver || uploading) && <div className="shimmer pointer-events-none absolute inset-0" />}

        <motion.div
          animate={dragOver ? { y: [-4, 4, -4] } : { y: [0, -8, 0] }}
          transition={{ duration: dragOver ? 0.6 : 3.2, repeat: Infinity, ease: 'easeInOut' }}
          className={cn(
            'relative mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl ring-1 transition-colors',
            dragOver ? 'bg-primary-500/20 ring-primary-500/40' : 'bg-primary-500/[0.07] ring-primary-500/20',
          )}
        >
          <CloudUpload size={26} className="text-primary-400" />
        </motion.div>

        <p className="relative text-sm font-semibold text-zinc-100">
          {uploading ? 'Uploading your files…' : dragOver ? 'Release to upload' : 'Drop files here, or click to browse'}
        </p>
        <p className="relative mt-1.5 text-[11px] leading-relaxed text-zinc-500">
          PDF, DOCX or TXT · up to 50 MB each · max 10 files
        </p>
        <p className="relative mt-1 text-[11px] leading-relaxed text-zinc-600">
          Scanned PDFs are read automatically with OCR.
        </p>

        <input
          ref={fileRef}
          type="file"
          multiple
          accept={ACCEPT}
          onChange={e => handleFiles(e.target.files)}
          className="hidden"
        />

        {uploading && (
          <div className="absolute inset-x-0 bottom-0 h-1 overflow-hidden bg-white/5">
            {phase === 'transfer' && progress > 0 ? (
              <motion.div
                className="h-full bg-gradient-to-r from-primary-500 to-primary-300"
                animate={{ width: `${progress}%` }}
                transition={{ ease: 'linear', duration: 0.2 }}
              />
            ) : (
              /* Server-side processing reports no progress — an indeterminate
                 sweep is the honest representation. */
              <motion.div
                className="h-full w-1/3 bg-gradient-to-r from-transparent via-primary-400 to-transparent"
                animate={{ x: ['-100%', '300%'] }}
                transition={{ duration: 1.1, repeat: Infinity, ease: 'linear' }}
              />
            )}
          </div>
        )}
      </motion.div>

      <AnimatePresence>
        {uploading && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-3 flex items-center gap-2.5 rounded-xl border border-primary-500/15 bg-primary-500/[0.05] px-3.5 py-2.5">
              <Loader2 size={14} className="shrink-0 animate-spin text-primary-400" />
              <p className="text-[12px] text-zinc-300">
                {phase === 'transfer'
                  ? <>Uploading… <span className="tabular-nums text-primary-300">{progress}%</span></>
                  : 'Queued for processing — extracting text and building embeddings.'}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** Inline result banner shown after an upload attempt. */
export function UploadResult({ ok, errors = [], onDismiss }) {
  if (!ok && !errors.length) return null
  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'mt-3 rounded-xl border px-3.5 py-3',
        errors.length ? 'border-amber-500/25 bg-amber-500/[0.06]' : 'border-success-500/25 bg-success-500/[0.06]',
      )}
    >
      <div className="flex items-start gap-2.5">
        {errors.length
          ? <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-400" />
          : <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-success-400" />}
        <div className="min-w-0 flex-1">
          {ok && <p className="text-[12px] font-medium text-zinc-200">{ok}</p>}
          {errors.length > 0 && (
            <ul className="mt-0.5 space-y-0.5">
              {errors.map((e, i) => (
                <li key={i} className="text-[12px] leading-relaxed text-amber-200/90">{e}</li>
              ))}
            </ul>
          )}
        </div>
        <button onClick={onDismiss} className="shrink-0 text-[11px] font-semibold text-zinc-500 hover:text-zinc-300">
          Dismiss
        </button>
      </div>
    </motion.div>
  )
}
