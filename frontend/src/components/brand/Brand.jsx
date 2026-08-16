import { memo } from 'react'
import { cn } from '../../lib/utils'

/**
 * Brand mark — an outlined brain drawn in metallic gold.
 *
 * Pure SVG so it stays crisp from the 26px navbar avatar up to the 220px hero
 * centrepiece. `id` suffixes the gradients so several marks on one page cannot
 * collide in the SVG id namespace.
 */
export const BrandMark = memo(function BrandMark({ size = 34, className, id = 'mark', stroke = 2 }) {
  const grad = `${id}-gold`
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn('shrink-0', className)}
      role="img"
      aria-label="RAG Chatbot"
    >
      <defs>
        <linearGradient id={grad} x1="10" y1="8" x2="54" y2="56" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#F7E7A8" />
          <stop offset="45%" stopColor="#F5C542" />
          <stop offset="100%" stopColor="#C99A41" />
        </linearGradient>
      </defs>

      <g stroke={`url(#${grad})`} strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" fill="none">
        {/* mirrored lobes */}
        <path d="M32 14.5c-3.9-3.6-10-2.9-12.4 1.1-4 .3-6.6 3.3-6.1 7-3.2 1.8-3.9 5.8-1.6 8.5-1.5 3.5.5 7.3 4.1 8.1.9 3.7 4.7 5.7 8.3 4.5 2 2.8 6.1 3.2 8.4.7" />
        <path d="M32 14.5c3.9-3.6 10-2.9 12.4 1.1 4 .3 6.6 3.3 6.1 7 3.2 1.8 3.9 5.8 1.6 8.5 1.5 3.5-.5 7.3-4.1 8.1-.9 3.7-4.7 5.7-8.3 4.5-2 2.8-6.1 3.2-8.4.7" />
        {/* stem */}
        <path d="M32 14.5v30.5" opacity="0.8" />
        {/* synapses */}
        <g strokeWidth={stroke * 0.72} opacity="0.7">
          <path d="M32 23c-3.2 0-4.9 1.9-4.9 4.3M32 31.5c3.2 0 4.9 1.8 4.9 4.2M32 27.3c2.8 0 4.4-1.7 4.4-4M32 36.4c-2.8 0-4.4 1.6-4.4 3.9" />
        </g>
        {/* base */}
        <path d="M26 49.5h12M28.5 54h7" strokeWidth={stroke * 0.85} opacity="0.55" />
      </g>

      {[
        [27.1, 27.3], [36.9, 23.3], [36.9, 35.7], [27.1, 40.3],
        [19.5, 22.8], [44.5, 22.8], [20.4, 38.4], [43.6, 38.4],
      ].map(([cx, cy], i) => (
        <circle key={i} cx={cx} cy={cy} r={i < 4 ? 1.9 : 1.5} fill={`url(#${grad})`} />
      ))}
    </svg>
  )
})

/** Wordmark: "RAG Chatbot" with the optional "AI-Powered Assistant" strapline. */
export function BrandName({ tagline = true, className, size = 'md' }) {
  const title = size === 'lg' ? 'text-2xl' : size === 'sm' ? 'text-base' : 'text-[1.35rem]'
  return (
    <span className={cn('flex flex-col leading-none', className)}>
      <span className={cn('font-display font-bold tracking-tight text-white', title)}>
        RAG <span className="text-primary-400">Chatbot</span>
      </span>
      {tagline && (
        <span className="mt-1 text-[11px] font-medium tracking-wide text-zinc-500">
          AI-Powered Assistant
        </span>
      )}
    </span>
  )
}

/** Mark + wordmark lock-up, as used in the navbar and on the auth pages. */
export default function Brand({ size = 34, tagline = true, className, id = 'brand', nameSize = 'md' }) {
  return (
    <span className={cn('inline-flex select-none items-center gap-3', className)}>
      <span className="relative inline-flex items-center justify-center">
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 -m-1 rounded-full blur-md"
          style={{ background: 'radial-gradient(circle, rgba(212,175,55,0.38), transparent 70%)' }}
        />
        <BrandMark size={size} id={id} className="relative" />
      </span>
      <BrandName tagline={tagline} size={nameSize} />
    </span>
  )
}
