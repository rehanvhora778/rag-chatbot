import { Logo } from './common'
import { PROJECT } from './portfolio'

export default function SiteFooter() {
  return (
    <footer className="border-t border-zinc-200/80 px-5 py-8 dark:border-white/10 sm:px-8">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-center justify-between gap-4 sm:flex-row">
        <Logo />

        <p className="text-xs lp-sub">
          © {new Date().getFullYear()} {PROJECT.name} — {PROJECT.type}, {PROJECT.college}.
        </p>

        <p className="text-xs lp-sub">Built with React, Django, FAISS &amp; Groq</p>
      </div>
    </footer>
  )
}
