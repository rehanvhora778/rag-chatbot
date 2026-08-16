import CountUp from 'react-countup'
import { Users } from 'lucide-react'
import { CARD, IconChip, Reveal } from './primitives'

const STATS = [
  { value: 10,   suffix: 'K+', label: 'Active Users' },
  { value: 50,   suffix: 'K+', label: 'Documents Analyzed' },
  { value: 99.9, suffix: '%',  label: 'Uptime', decimals: 1 },
]

/** Wireframe globe that fades into the right edge of the band. */
function Globe() {
  return (
    <svg viewBox="0 0 260 260" className="h-full w-full" aria-hidden>
      <defs>
        <radialGradient id="globe-core" cx="42%" cy="36%" r="70%">
          <stop offset="0%" stopColor="#F5C542" stopOpacity="0.22" />
          <stop offset="70%" stopColor="#D4AF37" stopOpacity="0.05" />
          <stop offset="100%" stopColor="#D4AF37" stopOpacity="0" />
        </radialGradient>
      </defs>

      <circle cx="130" cy="130" r="108" fill="url(#globe-core)" />
      <circle cx="130" cy="130" r="108" stroke="rgba(212,175,55,0.30)" strokeWidth="1" fill="none" />

      {/* latitudes */}
      {[36, 66, 90, 114, 144].map((ry, i) => (
        <ellipse key={i} cx="130" cy="130" rx="108" ry={ry * 0.42} stroke="rgba(212,175,55,0.18)" strokeWidth="0.9" fill="none" />
      ))}
      {/* longitudes */}
      {[18, 42, 70, 96].map((rx, i) => (
        <ellipse key={i} cx="130" cy="130" rx={rx} ry="108" stroke="rgba(212,175,55,0.16)" strokeWidth="0.9" fill="none" />
      ))}

      {/* network nodes + links */}
      {[[86, 92], [148, 74], [190, 132], [104, 168], [156, 196], [64, 140]].map(([cx, cy], i) => (
        <circle key={i} cx={cx} cy={cy} r={i % 2 ? 2.6 : 1.8} fill="#F5C542" opacity="0.85" />
      ))}
      <g stroke="rgba(245,197,66,0.35)" strokeWidth="0.8" fill="none">
        <path d="M86 92 Q120 60 148 74" />
        <path d="M148 74 Q186 96 190 132" />
        <path d="M190 132 Q160 176 156 196" />
        <path d="M104 168 Q78 156 64 140" />
        <path d="M86 92 Q68 122 64 140" />
      </g>
    </svg>
  )
}

export default function TrustBand() {
  return (
    <div className="px-5 pb-8 sm:px-8">
      <Reveal className="mx-auto w-full max-w-7xl">
        <div className={`${CARD} relative overflow-hidden`}>
          {/* globe bleeds off the right edge, behind the numbers */}
          <div className="pointer-events-none absolute -right-10 top-1/2 hidden h-[260px] w-[260px] -translate-y-1/2 opacity-70 md:block">
            <Globe />
          </div>

          <div className="relative grid gap-8 p-7 md:grid-cols-[1.1fr_1.6fr] md:items-center md:p-9">
            <div className="flex items-start gap-4">
              <IconChip icon={Users} size={46} />
              <div>
                <p className="font-display text-lg font-semibold leading-snug text-white">
                  Trusted by thousands<br className="hidden sm:block" /> of professionals
                </p>
                <p className="mt-2 text-[13px] leading-relaxed text-zinc-500">
                  Join our growing community of happy users.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              {STATS.map(({ value, suffix, label, decimals }) => (
                <div key={label} className="text-center md:text-left">
                  <p className="font-display text-3xl font-bold text-primary-400 sm:text-[2.1rem]">
                    <CountUp end={value} duration={1.8} decimals={decimals ?? 0} enableScrollSpy scrollSpyOnce />
                    {suffix}
                  </p>
                  <p className="mt-1 text-[13px] text-zinc-500">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Reveal>
    </div>
  )
}
