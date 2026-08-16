/** @type {import('tailwindcss').Config} */

/*
 * Premium black + metallic gold design system.
 *
 * The token NAMES are deliberately unchanged from the previous purple theme
 * (`primary`, `accent`, `ink`) so every component that already styles itself
 * with `primary-500` / `ink-800` inherits the new look without being touched.
 * Only the values moved.
 *
 *   primary → gold        (#D4AF37 core, #F5C542 bright, #E8C76A soft)
 *   accent  → warm bronze (pairs with gold in gradients without going orange)
 *   ink     → near-black  (cinematic, not blue-black)
 */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // ── Metallic gold ──
        primary: {
          50:  '#FCF9EE',
          100: '#F9F0D2',
          200: '#F3E4AC',
          300: '#E8C76A',   // soft gold  — body accents, icons
          400: '#F5C542',   // bright gold — highlights, active text
          500: '#D4AF37',   // primary gold — buttons, borders, brand
          600: '#B8912B',
          700: '#8E6F20',
          800: '#665016',
          900: '#42340E',
          950: '#231B07',
        },
        // ── Warm bronze — the darker half of gold gradients ──
        accent: {
          50:  '#FAF5EA',
          100: '#F3E8CE',
          200: '#E7D09E',
          300: '#D9B36A',
          400: '#C99A41',
          500: '#B07E28',
          600: '#93651E',
          700: '#734E18',
          800: '#523713',
          900: '#33220C',
        },
        success: {
          400: '#4ADE80',
          500: '#22C55E',
          600: '#16A34A',
        },
        // ── Cinematic near-black surfaces ──
        ink: {
          950: '#050506',   // page background
          900: '#0A0A0C',   // sidebar / chrome
          850: '#0F0F12',   // raised panels
          800: '#141417',   // cards
          700: '#1C1C21',   // hover / inputs
          600: '#26262C',   // borders on solids
          500: '#35353D',
        },
      },
      fontFamily: {
        sans:    ['Inter', 'system-ui', 'sans-serif'],
        display: ['"Space Grotesk"', 'Inter', 'sans-serif'],
        geist:   ['Geist', 'Inter', 'sans-serif'],
      },
      boxShadow: {
        // Gold is an accent, not a floodlight — these stay restrained.
        glow:       '0 0 24px rgba(212, 175, 55, 0.28)',
        'glow-sm':  '0 0 12px rgba(212, 175, 55, 0.18)',
        'glow-lg':  '0 0 60px rgba(212, 175, 55, 0.32)',
        'glow-accent': '0 0 24px rgba(176, 126, 40, 0.28)',
        card:       '0 1px 2px rgba(0,0,0,0.6), 0 8px 32px rgba(0,0,0,0.45)',
        'card-hover': '0 12px 48px rgba(0,0,0,0.6), 0 0 0 1px rgba(212,175,55,0.18)',
        // Thin inner highlight along the top edge — the "polished metal" cue.
        bevel:      'inset 0 1px 0 rgba(255,255,255,0.06)',
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'aurora':  'conic-gradient(from 180deg at 50% 50%, #D4AF37 0deg, #B07E28 120deg, #F5C542 240deg, #D4AF37 360deg)',
        'shimmer': 'linear-gradient(90deg, transparent 0%, rgba(245,197,66,0.10) 50%, transparent 100%)',
        // Brushed-metal sweep for headline text and premium buttons.
        'gold-metal': 'linear-gradient(110deg, #8E6F20 0%, #D4AF37 22%, #F7E7A8 45%, #F5C542 58%, #D4AF37 78%, #8E6F20 100%)',
      },
      animation: {
        'fade-in':    'fadeIn 0.4s ease-out both',
        'fade-up':    'fadeUp 0.5s cubic-bezier(0.22,1,0.36,1) both',
        'aurora':     'aurora 18s ease infinite',
        'gradient':   'gradientMove 6s ease infinite',
        'float':      'float 6s ease-in-out infinite',
        'float-slow': 'float 9s ease-in-out infinite',
        'shimmer':    'shimmer 1.8s linear infinite',
        'shine':      'shine 1.2s ease',
        'glow-pulse': 'glowPulse 2.4s ease-in-out infinite',
        'spin-slow':  'spin 2.4s linear infinite',
        'blink':      'blink 1s step-end infinite',
        'sheen':      'gradientMove 8s ease infinite',
      },
      keyframes: {
        fadeIn: { from: { opacity: 0 }, to: { opacity: 1 } },
        fadeUp: { from: { opacity: 0, transform: 'translateY(14px)' }, to: { opacity: 1, transform: 'translateY(0)' } },
        aurora: {
          '0%,100%': { transform: 'rotate(0deg) scale(1.4)' },
          '50%':     { transform: 'rotate(180deg) scale(1.7)' },
        },
        gradientMove: {
          '0%,100%': { backgroundPosition: '0% 50%' },
          '50%':     { backgroundPosition: '100% 50%' },
        },
        float: {
          '0%,100%': { transform: 'translateY(0) translateX(0)' },
          '50%':     { transform: 'translateY(-22px) translateX(8px)' },
        },
        shimmer: {
          '0%':   { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' },
        },
        shine: {
          '0%':   { transform: 'translateX(-120%) skewX(-18deg)' },
          '100%': { transform: 'translateX(220%) skewX(-18deg)' },
        },
        glowPulse: {
          '0%,100%': { boxShadow: '0 0 16px rgba(212,175,55,0.20)' },
          '50%':     { boxShadow: '0 0 38px rgba(212,175,55,0.45)' },
        },
        blink: { '0%,100%': { opacity: 1 }, '50%': { opacity: 0 } },
      },
    },
  },
  plugins: [],
}
