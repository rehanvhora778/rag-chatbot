import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import CountUp from 'react-countup'
import {
  FileText, MessageSquare, Search, Upload, ArrowUpRight,
  Sparkles, Plus, BookOpen,
} from 'lucide-react'
import toast from 'react-hot-toast'

import { analyticsAPI } from '../api/analytics'
import { useAuth } from '../contexts/AuthContext'
import Logo from '../components/ui/Logo'
import EmptyState from '../components/ui/EmptyState'
import AnimatedButton from '../components/ui/AnimatedButton'
import { SkeletonStatCard } from '../components/ui/LoadingSkeleton'

const container = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } }
const item = { hidden: { opacity: 0, y: 16 }, show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } } }

const statusStyle = {
  completed:  'bg-success-500/[0.12] text-success-400',
  processing: 'bg-primary-500/[0.12] text-primary-300',
  pending:    'bg-white/[0.05] text-zinc-400',
  failed:     'bg-red-500/[0.12] text-red-400',
}

function DashboardSkeleton() {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="card shimmer relative h-32 overflow-hidden" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {[0, 1, 2].map(i => <SkeletonStatCard key={i} />)}
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {[0, 1, 2].map(i => <div key={i} className="card shimmer relative h-20 overflow-hidden" />)}
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="card shimmer relative h-48 overflow-hidden" />
        <div className="card shimmer relative h-48 overflow-hidden" />
      </div>
    </div>
  )
}

function StatCard({ label, value, icon: Icon, to }) {
  return (
    <motion.div variants={item}>
      <Link to={to} className="surface-gold spotlight-card group flex items-center gap-4 p-5 transition-transform duration-200 hover:-translate-y-0.5">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-primary-500/20 to-accent-600/10 ring-1 ring-primary-500/20">
          <Icon size={20} className="text-primary-400" />
        </span>
        <span className="min-w-0">
          <span className="block text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-500">{label}</span>
          <span className="mt-0.5 block font-display text-2xl font-bold tabular-nums text-white">
            <CountUp end={value ?? 0} duration={1.3} separator="," />
          </span>
        </span>
        <ArrowUpRight size={15} className="ml-auto shrink-0 text-zinc-700 transition-colors group-hover:text-primary-400" />
      </Link>
    </motion.div>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    analyticsAPI.getDashboard()
      .then(res => setData(res.data.data))
      .catch(() => toast.error('Could not load your dashboard.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <DashboardSkeleton />

  const stats = data?.stats || {}
  const isNew = !stats.total_documents

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="mx-auto max-w-5xl space-y-6 pb-4">
      {/* Welcome */}
      <motion.div variants={item} className="surface-gold relative overflow-hidden p-5 sm:p-6">
        <div
          className="pointer-events-none absolute inset-0"
          style={{ background: 'radial-gradient(ellipse 55% 130% at 88% 45%, rgba(212,175,55,0.16), transparent 68%)' }}
        />
        <div className="relative flex items-center justify-between gap-4">
          <div className="min-w-0">
            <span className="chip mb-2"><Sparkles size={11} /> AI Workspace</span>
            <h2 className="font-display text-xl font-bold text-white sm:text-2xl">
              Welcome back,{' '}
              <span className="text-gradient-animated">{user?.full_name?.split(' ')[0] || user?.username}</span>
            </h2>
            <p className="mt-1 text-[13px] text-zinc-400">Here&apos;s an overview of your knowledge base.</p>
          </div>
          <motion.div
            animate={{ y: [0, -6, 0] }}
            transition={{ duration: 3.6, repeat: Infinity, ease: 'easeInOut' }}
            className="hidden shrink-0 sm:block"
          >
            <Logo size={56} id="dash" />
          </motion.div>
        </div>
      </motion.div>

      {isNew ? (
        <motion.div variants={item} className="surface-gold">
          <EmptyState
            icon={BookOpen}
            title="Build Your Knowledge Base"
            description="Upload PDFs and start asking questions about your documents."
            actions={
              <>
                <Link to="/documents"><AnimatedButton><Upload size={14} /> Upload Document</AnimatedButton></Link>
                <a href="https://research.ibm.com/blog/retrieval-augmented-generation-RAG" target="_blank" rel="noopener noreferrer">
                  <AnimatedButton variant="secondary">Learn How RAG Works</AnimatedButton>
                </a>
              </>
            }
          />
        </motion.div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard label="Documents"     value={stats.total_documents} icon={FileText}      to="/documents" />
            <StatCard label="Chat Sessions" value={stats.total_sessions}  icon={MessageSquare} to="/chat" />
            <StatCard label="Questions"     value={stats.total_queries}   icon={Search}        to="/analytics" />
          </div>

          {/* Quick actions */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {[
              { to: '/chat?new=1', icon: Plus,   title: 'Start New Chat',  sub: 'Ask across your documents' },
              { to: '/documents',  icon: Upload, title: 'Upload Document', sub: 'PDF, DOCX or TXT' },
            ].map(({ to, icon: Icon, title, sub }) => (
              <motion.div variants={item} key={to}>
                <Link to={to} className="spotlight-card group flex items-center gap-3.5 rounded-2xl border border-white/[0.06] bg-ink-800/60 p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary-500/30">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-500/10 ring-1 ring-primary-500/20 transition-transform duration-200 group-hover:scale-110">
                    <Icon size={17} className="text-primary-400" />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-semibold text-white">{title}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-zinc-500">{sub}</span>
                  </span>
                  <ArrowUpRight size={15} className="ml-auto shrink-0 text-zinc-700 transition-colors group-hover:text-primary-400" />
                </Link>
              </motion.div>
            ))}
          </div>

          {/* Recent */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <motion.div variants={item} className="surface-gold p-5">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">Recent Documents</h3>
                <Link to="/documents" className="text-[11px] font-semibold text-primary-400 hover:text-primary-300">View all</Link>
              </div>
              {data?.recent_documents?.length ? (
                <div className="divide-y divide-white/[0.05]">
                  {data.recent_documents.map(d => (
                    <div key={d.id} className="flex items-center justify-between gap-3 py-2.5">
                      <div className="flex min-w-0 items-center gap-2.5">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary-500/10">
                          <FileText size={12} className="text-primary-400" />
                        </span>
                        <span className="truncate text-[13px] text-zinc-300">{d.original_filename}</span>
                      </div>
                      <span className={`badge shrink-0 ${statusStyle[d.status] || ''}`}>{d.status}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="py-8 text-center text-[13px] text-zinc-500">No documents yet.</p>
              )}
            </motion.div>

            <motion.div variants={item} className="surface-gold p-5">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">Recent Chats</h3>
                <Link to="/chat" className="text-[11px] font-semibold text-primary-400 hover:text-primary-300">View all</Link>
              </div>
              {data?.recent_sessions?.length ? (
                <div className="divide-y divide-white/[0.05]">
                  {data.recent_sessions.map(s => (
                    <Link key={s.id} to={`/chat/${s.id}`} className="group flex items-center gap-2.5 py-2.5">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary-500/10">
                        <MessageSquare size={12} className="text-primary-400" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] text-zinc-300 transition-colors group-hover:text-primary-200">{s.title}</span>
                        <span className="block truncate text-[10px] text-zinc-600">
                          {s.last_message_preview || `${s.message_count || 0} messages`}
                        </span>
                      </span>
                      <ArrowUpRight size={13} className="shrink-0 text-zinc-700 transition-colors group-hover:text-primary-400" />
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="py-8 text-center text-[13px] text-zinc-500">No chats yet.</p>
              )}
            </motion.div>
          </div>
        </>
      )}
    </motion.div>
  )
}
