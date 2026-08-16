import { memo } from 'react'
import { cn } from '../../lib/utils'

/**
 * Brand mark — a neural/brain glyph inside a gold ring. Pure SVG, no raster.
 *
 * The glyph reads as a brain in silhouette but is built from a symmetrical
 * node-and-synapse lattice, which is what keeps it legible at 26px in a message
 * avatar as well as at 64px on the dashboard.
 *
 * `id` suffixes every gradient so several Logos on one page can't collide in
 * the SVG id namespace.
 */
function Logo({ size = 40, className, glow = true, id = 'brand' }) {
  const ring = `${id}-ring`
  const core = `${id}-core`

  return (
    <span
      className={cn('relative inline-flex shrink-0 items-center justify-center', className)}
      style={{ width: size, height: size }}
    >
      {glow && (
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-full blur-md"
          style={{ background: 'radial-gradient(circle, rgba(212,175,55,0.42), transparent 70%)' }}
        />
      )}

      <svg
        width={size}
        height={size}
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="relative"
        role="img"
        aria-label="RAG Chatbot"
      >
        <defs>
          <linearGradient id={ring} x1="10" y1="6" x2="54" y2="58" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#F7E7A8" />
            <stop offset="42%"  stopColor="#F5C542" />
            <stop offset="78%"  stopColor="#D4AF37" />
            <stop offset="100%" stopColor="#8E6F20" />
          </linearGradient>
          <linearGradient id={core} x1="18" y1="16" x2="46" y2="48" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#FCF3D2" />
            <stop offset="50%"  stopColor="#F5C542" />
            <stop offset="100%" stopColor="#C99A41" />
          </linearGradient>
        </defs>

        {/* Bezel */}
        <circle cx="32" cy="32" r="29.5" fill="#0A0A0C" stroke={`url(#${ring})`} strokeWidth="2" />
        <circle cx="32" cy="32" r="25.5" stroke={`url(#${ring})`} strokeWidth="0.7" opacity="0.28" />

        {/* Brain silhouette — two mirrored lobes */}
        <g stroke={`url(#${core})`} strokeWidth="1.9" strokeLinecap="round" fill="none">
          <path d="M32 19.5c-3.2-3-8.2-2.4-10.2.9-3.3.2-5.4 2.7-5 5.7-2.6 1.5-3.2 4.8-1.3 7-1.2 2.9.4 6 3.4 6.7.7 3 3.8 4.7 6.8 3.7 1.7 2.3 5 2.6 6.9.6" />
          <path d="M32 19.5c3.2-3 8.2-2.4 10.2.9 3.3.2 5.4 2.7 5 5.7 2.6 1.5 3.2 4.8 1.3 7 1.2 2.9-.4 6-3.4 6.7-.7 3-3.8 4.7-6.8 3.7-1.7 2.3-5 2.6-6.9.6" />
          {/* Central stem */}
          <path d="M32 19.5v25" opacity="0.75" />
          {/* Synapses */}
          <path d="M32 26.5c-2.6 0-4 1.6-4 3.6M32 33.5c2.6 0 4 1.5 4 3.5M32 30c2.3 0 3.6-1.4 3.6-3.3M32 37.5c-2.3 0-3.6 1.3-3.6 3.2"
                strokeWidth="1.4" opacity="0.62" />
        </g>

        {/* Nodes */}
        {[
          [28, 30.1], [36, 26.7], [36, 37], [28.4, 40.7],
          [21.6, 26.4], [42.4, 26.4], [22.4, 39.3], [41.6, 39.3],
        ].map(([cx, cy], i) => (
          <circle key={i} cx={cx} cy={cy} r={i < 4 ? 1.9 : 1.5} fill={`url(#${core})`} />
        ))}
      </svg>
    </span>
  )
}

export default memo(Logo)
