import { memo } from 'react'
import { BrandMark } from '../brand/Brand'

/**
 * Full-bleed backdrop for the auth brand panel: a dark valley with a lit path
 * winding up towards a glowing brain — "your RAG journey" as a picture.
 *
 * Drawn as SVG and sliced like a cover image, so it fills a panel of any height
 * without distorting and ships no image bytes. A scrim at the top keeps the
 * headline overlaid on it legible.
 */
function ValleyArt({ className }) {
  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${className || ''}`} aria-hidden>
      <svg
        viewBox="0 0 600 900"
        preserveAspectRatio="xMidYMid slice"
        className="absolute inset-0 h-full w-full"
      >
        <defs>
          <linearGradient id="va-sky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#080705" />
            <stop offset="45%" stopColor="#13100a" />
            <stop offset="100%" stopColor="#050403" />
          </linearGradient>
          <linearGradient id="va-far" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2e2415" />
            <stop offset="100%" stopColor="#0d0b07" />
          </linearGradient>
          <linearGradient id="va-mid" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3d2e18" />
            <stop offset="100%" stopColor="#0a0806" />
          </linearGradient>
          <linearGradient id="va-near" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1a1309" />
            <stop offset="100%" stopColor="#050403" />
          </linearGradient>
          <linearGradient id="va-path" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="#F7E7A8" />
            <stop offset="55%" stopColor="#F5C542" />
            <stop offset="100%" stopColor="#D4AF37" />
          </linearGradient>
          <radialGradient id="va-halo" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#F5C542" stopOpacity="0.55" />
            <stop offset="52%" stopColor="#D4AF37" stopOpacity="0.13" />
            <stop offset="100%" stopColor="#D4AF37" stopOpacity="0" />
          </radialGradient>
          <filter id="va-blur" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="11" />
          </filter>
        </defs>

        <rect width="600" height="900" fill="url(#va-sky)" />

        {/* stars */}
        {[
          [64, 88], [138, 152], [212, 62], [286, 128], [352, 74], [430, 142],
          [498, 96], [552, 178], [96, 210], [268, 218], [386, 196], [520, 44],
        ].map(([cx, cy], i) => (
          <circle key={i} cx={cx} cy={cy} r={i % 3 === 0 ? 1.6 : 1} fill="#F5C542" opacity={0.22 + (i % 4) * 0.11} />
        ))}

        {/* glow pooling around the summit */}
        <circle cx="300" cy="430" r="230" fill="url(#va-halo)" />

        {/* ridges, far to near */}
        <path d="M0 520 L92 402 L172 470 L262 348 L360 486 L442 414 L540 500 L600 452 L600 900 L0 900 Z" fill="url(#va-far)" opacity="0.85" />
        <path d="M0 612 L86 512 L184 596 L300 470 L404 590 L500 518 L600 610 L600 900 L0 900 Z" fill="url(#va-mid)" opacity="0.92" />
        <path d="M0 726 L118 636 L240 710 L344 640 L466 718 L600 664 L600 900 L0 900 Z" fill="url(#va-near)" />

        {/* the lit path — soft glow pass, then the crisp line */}
        <path
          d="M300 486 C294 552 250 580 218 626 C182 678 246 706 276 748 C312 798 224 826 188 862 C170 880 158 890 152 900"
          stroke="#F5C542" strokeWidth="14" strokeLinecap="round" fill="none" opacity="0.35" filter="url(#va-blur)"
        />
        <path
          d="M300 486 C294 552 250 580 218 626 C182 678 246 706 276 748 C312 798 224 826 188 862 C170 880 158 890 152 900"
          stroke="url(#va-path)" strokeWidth="4" strokeLinecap="round" fill="none"
        />
      </svg>

      {/* the brand mark sits at the summit, glowing */}
      <div className="absolute left-1/2 top-[46%] -translate-x-1/2 -translate-y-1/2">
        <span
          className="absolute inset-0 -m-8 rounded-full blur-2xl"
          style={{ background: 'radial-gradient(circle, rgba(245,197,66,0.5), transparent 70%)' }}
        />
        <BrandMark size={62} id="valley" className="relative animate-glow-pulse rounded-full" />
      </div>

      {/* scrim: keeps the overlaid headline readable, fades the art into the page */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'linear-gradient(to bottom, rgba(5,5,6,0.94) 0%, rgba(5,5,6,0.62) 22%, rgba(5,5,6,0) 45%),' +
            'linear-gradient(to right, rgba(5,5,6,0.35), transparent 40%)',
        }}
      />
    </div>
  )
}

export default memo(ValleyArt)
