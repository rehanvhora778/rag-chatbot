import { Link } from 'react-router-dom'
import Brand from '../brand/Brand'
import { PROJECT } from '../landing/portfolio'

const COLUMNS = [
  {
    title: 'Product',
    links: [
      { label: 'Features',     href: '#features' },
      { label: 'How It Works', href: '#how-it-works' },
      { label: 'Docs',         href: '#docs' },
    ],
  },
  {
    title: 'Account',
    links: [
      { label: 'Login',        to: '/login' },
      { label: 'Register',     to: '/register' },
      { label: 'Admin Login',  to: '/admin-login' },
    ],
  },
  {
    title: 'Legal',
    links: [
      { label: 'Privacy Policy',   to: '/privacy' },
      { label: 'Terms of Service', to: '/terms' },
      { label: 'Contact',          href: `mailto:${PROJECT.email}` },
    ],
  },
]

const linkCls = 'text-sm text-zinc-500 transition-colors hover:text-primary-400'

export default function HomeFooter() {
  return (
    <footer className="border-t border-white/[0.07] px-5 py-12 sm:px-8">
      <div className="mx-auto w-full max-w-7xl">
        <div className="grid gap-10 md:grid-cols-[1.4fr_repeat(3,1fr)]">
          <div>
            <Brand size={32} nameSize="sm" />
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-zinc-500">
              Retrieve, understand and interact with your documents — grounded in your own files,
              with every answer cited.
            </p>
          </div>

          {COLUMNS.map(col => (
            <div key={col.title}>
              <p className="text-sm font-semibold text-white">{col.title}</p>
              <ul className="mt-4 space-y-2.5">
                {col.links.map(l => (
                  <li key={l.label}>
                    {l.to ? (
                      <Link to={l.to} className={linkCls}>{l.label}</Link>
                    ) : (
                      <a href={l.href} className={linkCls}>{l.label}</a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-10 flex flex-col items-center justify-between gap-3 border-t border-white/[0.07] pt-6 text-xs text-zinc-600 sm:flex-row">
          <p>© {new Date().getFullYear()} RAG Chatbot — {PROJECT.type}, {PROJECT.college}.</p>
          <p>Built with React, Django, FAISS &amp; Groq.</p>
        </div>
      </div>
    </footer>
  )
}
