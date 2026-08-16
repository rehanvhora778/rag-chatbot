import { useEffect, useRef } from 'react'
import { cn } from '../../lib/utils'

/**
 * Six separate boxes that behave like one field.
 *
 * `value` is the plain digit string — the boxes are just a presentation of it,
 * so the parent never has to reassemble anything. Typing advances, backspace
 * retreats, and pasting a whole code from the email fills every box at once.
 */
export default function OtpInput({
  value = '',
  onChange,
  onComplete,
  length = 6,
  disabled = false,
  error = false,
  autoFocus = true,
}) {
  const refs = useRef([])

  useEffect(() => {
    if (autoFocus && !disabled) refs.current[0]?.focus()
  }, [autoFocus, disabled])

  const focusAt = i => refs.current[Math.max(0, Math.min(i, length - 1))]?.focus()

  const commit = next => {
    const clean = next.replace(/\D/g, '').slice(0, length)
    onChange(clean)
    if (clean.length === length) onComplete?.(clean)
    return clean
  }

  const handleChange = (i, raw) => {
    const typed = raw.replace(/\D/g, '')
    if (!typed) return
    // Autofill (and one-tap SMS/email suggestions) can drop the whole code into
    // a single box, so spread whatever arrived across the boxes from here on.
    const next = (value.slice(0, i) + typed + value.slice(i + typed.length)).slice(0, length)
    commit(next)
    focusAt(i + typed.length)
  }

  const handleKeyDown = (i, e) => {
    if (e.key === 'Backspace') {
      e.preventDefault()
      if (value[i]) {
        commit(value.slice(0, i) + value.slice(i + 1))
      } else if (i > 0) {
        commit(value.slice(0, i - 1) + value.slice(i))
        focusAt(i - 1)
      }
      return
    }
    if (e.key === 'ArrowLeft')  { e.preventDefault(); focusAt(i - 1) }
    if (e.key === 'ArrowRight') { e.preventDefault(); focusAt(i + 1) }
  }

  const handlePaste = e => {
    e.preventDefault()
    const pasted = (e.clipboardData.getData('text') || '').replace(/\D/g, '')
    if (!pasted) return
    const next = commit(pasted)
    focusAt(next.length)
  }

  return (
    <div className="flex justify-center gap-2 sm:gap-2.5" onPaste={handlePaste}>
      {Array.from({ length }).map((_, i) => (
        <input
          key={i}
          ref={el => { refs.current[i] = el }}
          type="text"
          inputMode="numeric"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          maxLength={length}
          value={value[i] || ''}
          disabled={disabled}
          aria-label={`Digit ${i + 1} of ${length}`}
          onChange={e => handleChange(i, e.target.value)}
          onKeyDown={e => handleKeyDown(i, e)}
          onFocus={e => e.target.select()}
          className={cn(
            'h-12 w-11 rounded-xl border text-center font-display text-xl font-bold sm:h-14 sm:w-12 sm:text-2xl',
            'border-white/10 bg-white/[0.03] text-white caret-primary-400',
            'outline-none transition-all duration-200',
            'hover:border-white/20 focus:border-primary-500/70 focus:ring-2 focus:ring-primary-500/25',
            'disabled:cursor-not-allowed disabled:opacity-50',
            value[i] && 'border-primary-500/45 bg-primary-500/[0.07]',
            error && 'border-red-500/70 focus:border-red-500/70 focus:ring-red-500/20',
          )}
        />
      ))}
    </div>
  )
}
