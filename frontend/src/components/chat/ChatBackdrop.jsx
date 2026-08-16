import { memo } from 'react'

/**
 * Cinematic backdrop behind the chat transcript.
 *
 * Layered mountain ridges receding into a warm horizon glow, drawn entirely in
 * SVG — no stock photography. It sits behind the messages at low opacity and is
 * `pointer-events-none`, so it never competes with the content for contrast or
 * interaction. Ridges get lighter and hazier with distance to fake aerial
 * perspective, and the glow pools where the ridgelines converge.
 */
function ChatBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {/* Warm light pooling low and right, like a sun just under the ridge */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 60% 45% at 72% 88%, rgba(212,175,55,0.20), transparent 66%),' +
            'radial-gradient(ellipse 80% 40% at 30% 100%, rgba(176,126,40,0.13), transparent 70%)',
        }}
      />

      <svg
        viewBox="0 0 1200 620"
        preserveAspectRatio="xMidYMax slice"
        className="absolute inset-x-0 bottom-0 h-full w-full"
      >
        <defs>
          <linearGradient id="cb-far" x1="0" y1="300" x2="0" y2="620" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#4A3A14" stopOpacity="0.30" />
            <stop offset="100%" stopColor="#0A0A0C" stopOpacity="0.06" />
          </linearGradient>
          <linearGradient id="cb-mid" x1="0" y1="360" x2="0" y2="620" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#2A2009" stopOpacity="0.62" />
            <stop offset="100%" stopColor="#08080A" stopOpacity="0.30" />
          </linearGradient>
          <linearGradient id="cb-near" x1="0" y1="420" x2="0" y2="620" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#0D0D10" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#050506" stopOpacity="1" />
          </linearGradient>
          {/* Rim light that traces the near ridgeline */}
          <linearGradient id="cb-rim" x1="0" y1="0" x2="1200" y2="0" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stopColor="#D4AF37" stopOpacity="0" />
            <stop offset="42%"  stopColor="#F5C542" stopOpacity="0.55" />
            <stop offset="68%"  stopColor="#F7E7A8" stopOpacity="0.75" />
            <stop offset="100%" stopColor="#D4AF37" stopOpacity="0.10" />
          </linearGradient>
        </defs>

        {/* Far ridge */}
        <path
          d="M0 470 L120 396 L232 448 L348 350 L470 452 L596 372 L714 456 L840 386 L968 460 L1090 404 L1200 462 L1200 620 L0 620 Z"
          fill="url(#cb-far)"
        />
        {/* Middle ridge */}
        <path
          d="M0 528 L146 452 L268 512 L396 424 L520 508 L654 440 L790 516 L918 452 L1046 522 L1200 466 L1200 620 L0 620 Z"
          fill="url(#cb-mid)"
        />
        {/* Near ridge + its lit edge */}
        <path
          d="M0 580 L128 526 L262 574 L398 502 L536 570 L680 516 L818 578 L960 520 L1104 572 L1200 538 L1200 620 L0 620 Z"
          fill="url(#cb-near)"
        />
        <path
          d="M0 580 L128 526 L262 574 L398 502 L536 570 L680 516 L818 578 L960 520 L1104 572 L1200 538"
          fill="none"
          stroke="url(#cb-rim)"
          strokeWidth="1.6"
        />
      </svg>

      {/* Fade the whole thing out toward the top so message text always wins */}
      <div
        className="absolute inset-0"
        style={{ background: 'linear-gradient(to bottom, #050506 6%, rgba(5,5,6,0.72) 34%, rgba(5,5,6,0.34) 62%, transparent 100%)' }}
      />
    </div>
  )
}

export default memo(ChatBackdrop)
