import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import CountUp from 'react-countup'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts'
import {
  FileText, MessageSquare, Download, TrendingUp, Upload,
  Activity, Trophy, BarChart2,
} from 'lucide-react'
import toast from 'react-hot-toast'

import { analyticsAPI } from '../api/analytics'
import EmptyState from '../components/ui/EmptyState'
import AnimatedButton from '../components/ui/AnimatedButton'
import LoadingSkeleton, { SkeletonStatCard, SkeletonChart } from '../components/ui/LoadingSkeleton'

/* Gold-family series colours — distinguishable in the pie without leaving the
   palette, warmest first so the largest slice reads as the brightest. */
const COLORS = ['#F5C542', '#D4AF37', '#B07E28', '#8E6F20', '#E8C76A']

const item = { hidden: { opacity: 0, y: 16 }, show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] } } }

const ACTIVITY_ICON = {
  document_upload: Upload,
  chat_query:      MessageSquare,
  pdf_export:      Download,
  summary_generated: FileText,
}

function StatCard({ label, value, icon: Icon, sub }) {
  return (
    <motion.div variants={item} className="surface-gold p-4 sm:p-5">
      <div className="mb-3 flex items-start justify-between gap-2">
        <p className="min-w-0 truncate text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-500">{label}</p>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500/20 to-accent-600/10 ring-1 ring-primary-500/20">
          <Icon size={15} className="text-primary-400" />
        </div>
      </div>
      <p className="font-display text-2xl font-bold tabular-nums text-white">
        <CountUp end={value ?? 0} duration={1.3} separator="," />
      </p>
      {sub && <p className="mt-1 truncate text-[11px] text-zinc-500">{sub}</p>}
    </motion.div>
  )
}

const ChartTooltip = ({ active, payload, label, unit = 'queries' }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-primary-500/25 bg-ink-850/[0.97] px-3 py-2 text-xs shadow-glow-sm backdrop-blur-xl">
      {label && <p className="mb-1 text-zinc-500">{label}</p>}
      <p className="font-bold text-white">
        {payload[0].value} {unit}
      </p>
    </div>
  )
}

function timeAgo(iso) {
  if (!iso) return ''
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (Number.isNaN(secs)) return ''
  if (secs < 60)    return 'just now'
  if (secs < 3600)  return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}

export default function AnalyticsPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    analyticsAPI.getUserAnalytics()
      .then(res => setData(res.data.data))
      .catch(() => toast.error('Could not load your analytics.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="space-y-2">
          <LoadingSkeleton className="h-7 w-40" />
          <LoadingSkeleton className="h-3 w-64" />
        </div>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[0, 1, 2, 3].map(i => <SkeletonStatCard key={i} />)}
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <SkeletonChart />
          <SkeletonChart />
        </div>
      </div>
    )
  }
  if (!data) return null

  const pieData = Object.entries(data.documents.by_type || {}).map(([name, value]) => ({ name: name.toUpperCase(), value }))
  const hasQueries = (data.daily_query_trend || []).some(d => d.queries > 0)
  const mostUsed = data.most_used_documents || []
  const activity = data.recent_activity || []
  const isEmpty = data.documents.total === 0 && data.chat.total_sessions === 0

  if (isEmpty) {
    return (
      <div className="mx-auto max-w-3xl">
        <h2 className="page-title">Analytics</h2>
        <p className="page-subtitle mb-6">Your usage statistics and activity overview</p>
        <div className="surface-gold">
          <EmptyState
            icon={BarChart2}
            title="Nothing to measure yet"
            description="Upload a document and ask a few questions — your usage will start appearing here."
            actions={
              <Link to="/documents"><AnimatedButton><Upload size={14} /> Upload Document</AnimatedButton></Link>
            }
          />
        </div>
      </div>
    )
  }

  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.055 } } }}
      className="mx-auto max-w-6xl space-y-6 pb-4"
    >
      <motion.div variants={item}>
        <h2 className="page-title">Analytics</h2>
        <p className="page-subtitle">Your usage statistics and activity overview</p>
      </motion.div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard label="Documents"     value={data.documents.total}          icon={FileText}      sub={`${data.documents.this_week} added this week`} />
        <StatCard label="Chat Sessions" value={data.chat.total_sessions}      icon={MessageSquare} sub={`${data.chat.active_sessions} active`} />
        <StatCard label="Questions"     value={data.chat.user_queries}        icon={TrendingUp}    sub={`${data.activity.queries_last_30d} in last 30 days`} />
        <StatCard label="Exports"       value={data.activity.exports_last_30d} icon={Download}     sub="Last 30 days" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
        <motion.div variants={item} className="surface-gold p-4 sm:p-5">
          <h3 className="mb-5 text-sm font-semibold text-white">Daily Questions — Last 7 Days</h3>
          {!hasQueries ? (
            <div className="flex h-[190px] items-center justify-center text-center text-[13px] text-zinc-500">
              No questions asked in the last seven days.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={data.daily_query_trend} margin={{ top: 0, right: 0, left: -22, bottom: 0 }}>
                <defs>
                  <linearGradient id="barFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"   stopColor="#F5C542" />
                    <stop offset="100%" stopColor="#8E6F20" />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(212,175,55,0.08)" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#71717a' }} tickFormatter={d => d.slice(5)} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#71717a' }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(212,175,55,0.07)' }} />
                <Bar dataKey="queries" fill="url(#barFill)" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </motion.div>

        <motion.div variants={item} className="surface-gold p-4 sm:p-5">
          <h3 className="mb-5 text-sm font-semibold text-white">Documents by Type</h3>
          {pieData.length === 0 ? (
            <div className="flex h-[190px] items-center justify-center text-[13px] text-zinc-500">No documents yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={190}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={75} dataKey="value" nameKey="name" stroke="none" paddingAngle={2}>
                  {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip content={<ChartTooltip unit="docs" />} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: '#a1a1aa' }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </motion.div>
      </div>

      {/* Most used documents + recent activity */}
      <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
        <motion.div variants={item} className="surface-gold p-4 sm:p-5">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <Trophy size={14} className="text-primary-400" /> Most Used Documents
          </h3>
          {mostUsed.length === 0 ? (
            <p className="py-8 text-center text-[13px] text-zinc-500">
              No document has been used in a conversation yet.
            </p>
          ) : (
            <div className="space-y-2.5">
              {mostUsed.map((d, i) => {
                const max = mostUsed[0].queries || 1
                const pct = Math.max(4, Math.round((d.queries / max) * 100))
                return (
                  <div key={d.document_id}>
                    <div className="mb-1 flex items-baseline justify-between gap-3">
                      <span className="min-w-0 truncate text-[12px] text-zinc-300">
                        <span className="mr-1.5 font-geist text-[10px] text-primary-500/70">{i + 1}</span>
                        {d.name}
                      </span>
                      <span className="shrink-0 text-[11px] tabular-nums text-zinc-500">
                        {d.queries} question{d.queries !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${pct}%` }}
                        transition={{ duration: 0.7, delay: i * 0.07, ease: [0.22, 1, 0.36, 1] }}
                        className="h-full rounded-full bg-gradient-to-r from-accent-600 to-primary-400"
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </motion.div>

        <motion.div variants={item} className="surface-gold p-4 sm:p-5">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <Activity size={14} className="text-primary-400" /> Recent Activity
          </h3>
          {activity.length === 0 ? (
            <p className="py-8 text-center text-[13px] text-zinc-500">No activity recorded yet.</p>
          ) : (
            <div className="max-h-[260px] space-y-0.5 overflow-y-auto pr-1">
              {activity.map((a, i) => {
                const Icon = ACTIVITY_ICON[a.event_type] || Activity
                return (
                  <div key={i} className="flex items-center gap-2.5 rounded-lg px-1.5 py-2 transition-colors hover:bg-white/[0.03]">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary-500/10 ring-1 ring-primary-500/15">
                      <Icon size={12} className="text-primary-400" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12px] text-zinc-300">{a.label}</span>
                      {a.detail && <span className="block truncate text-[10px] text-zinc-600">{a.detail}</span>}
                    </span>
                    <span className="shrink-0 text-[10px] text-zinc-600">{timeAgo(a.created_at)}</span>
                  </div>
                )
              })}
            </div>
          )}
        </motion.div>
      </div>

      {/* Processing */}
      <motion.div variants={item} className="surface-gold p-4 sm:p-5">
        <h3 className="mb-4 text-sm font-semibold text-white">Document Processing</h3>
        <div className="grid grid-cols-3 gap-3 sm:gap-4">
          {[
            { label: 'Ready',     value: data.documents.completed, color: 'text-success-400' },
            { label: 'Failed',    value: data.documents.failed,    color: 'text-red-400' },
            { label: 'This Week', value: data.documents.this_week, color: 'text-primary-300' },
          ].map(({ label, value, color }) => (
            <div key={label} className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4 text-center sm:p-5">
              <p className={`font-display text-2xl font-bold tabular-nums sm:text-3xl ${color}`}>
                <CountUp end={value ?? 0} duration={1.2} />
              </p>
              <p className="mt-1 text-[11px] font-medium text-zinc-400">{label}</p>
            </div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  )
}
