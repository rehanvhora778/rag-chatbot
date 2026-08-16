import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { adminAPI } from '../api/analytics'
import { useAuth } from '../contexts/AuthContext'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line,
} from 'recharts'
import {
  Users, FileText, MessageSquare, ShieldCheck, Trash2,
  ToggleLeft, ToggleRight, Search, X, ChevronLeft, ChevronRight,
  CheckCircle, XCircle, Clock, RefreshCw, Crown, UserCheck, UserX,
  MessagesSquare, Eye,
} from 'lucide-react'
import { PageLoader } from '../components/common/LoadingSpinner'
import GradientBorderCard from '../components/ui/GradientBorderCard'
import GlassCard from '../components/ui/GlassCard'
import CountUp from 'react-countup'
import toast from 'react-hot-toast'

// ─── helpers ──────────────────────────────────────────────────────────────
function fmt(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}
function fmtTime(d) {
  if (!d) return 'Never'
  return new Date(d).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const BADGE = {
  green:  'bg-success-500/15 text-success-400',
  red:    'bg-red-500/15 text-red-400',
  blue:   'bg-accent-500/15 text-accent-300',
  yellow: 'bg-amber-500/15 text-amber-400',
  gray:   'bg-white/5 text-zinc-400',
  purple: 'bg-primary-500/15 text-primary-300',
}
function Badge({ children, color = 'gray' }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${BADGE[color]}`}>{children}</span>
}

function StatCard({ label, value, icon: Icon, gradient, sub }) {
  return (
    <GradientBorderCard innerClassName="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">{label}</p>
          <p className="mt-1 font-display text-3xl font-bold text-white">
            <CountUp end={value ?? 0} duration={1.3} separator="," />
          </p>
          {sub && <p className="mt-1 text-xs text-zinc-500">{sub}</p>}
        </div>
        <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${gradient} shadow-glow-sm`}>
          <Icon size={20} className="text-white" />
        </div>
      </div>
    </GradientBorderCard>
  )
}

function Pagination({ page, total, pageSize, onChange }) {
  const totalPages = Math.ceil(total / pageSize)
  if (totalPages <= 1) return null
  return (
    <div className="flex items-center justify-between border-t border-white/[0.06] px-4 py-3">
      <span className="text-xs text-zinc-500">Page {page} of {totalPages} ({total} total)</span>
      <div className="flex gap-1">
        <button onClick={() => onChange(page - 1)} disabled={page === 1} className="rounded-lg p-1.5 text-zinc-400 hover:bg-white/5 disabled:opacity-40">
          <ChevronLeft size={14} />
        </button>
        <button onClick={() => onChange(page + 1)} disabled={page >= totalPages} className="rounded-lg p-1.5 text-zinc-400 hover:bg-white/5 disabled:opacity-40">
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  )
}

function SearchBar({ value, onChange, placeholder }) {
  return (
    <div className="relative">
      <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
      <input className="input-field w-64 py-2 pl-9 pr-8 text-sm" placeholder={placeholder} value={value} onChange={e => onChange(e.target.value)} />
      {value && (
        <button onClick={() => onChange('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300">
          <X size={13} />
        </button>
      )}
    </div>
  )
}

// ─── User Detail Modal ──────────────────────────────────────────────────────
function UserModal({ user, onClose, onUpdate }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    adminAPI.getUser(user.id).then(r => setDetail(r.data.data)).finally(() => setLoading(false))
  }, [user.id])

  const toggle = (field, val) => {
    adminAPI.updateUser(user.id, { [field]: val })
      .then(() => { toast.success('Updated'); onUpdate(user.id, { [field]: val }) })
      .catch(() => toast.error('Update failed'))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="absolute inset-0 bg-black/70 backdrop-blur-md" />
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 26 }}
        className="relative max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-white/10 bg-ink-850/95 backdrop-blur-2xl shadow-glow-sm"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/[0.06] p-5">
          <h3 className="font-display font-semibold text-white">User Details</h3>
          <button onClick={onClose} className="rounded-lg p-1 text-zinc-400 hover:bg-white/10 hover:text-white"><X size={16} /></button>
        </div>

        {loading ? (
          <div className="p-8 text-center text-zinc-500">Loading…</div>
        ) : detail && (
          <div className="space-y-5 p-5">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-accent-600 text-xl font-bold text-white shadow-glow-sm">
                {detail.user.username[0].toUpperCase()}
              </div>
              <div>
                <p className="text-lg font-semibold text-white">{detail.user.username}</p>
                <p className="text-sm text-zinc-500">{detail.user.email || 'No email'}</p>
                <div className="mt-1 flex gap-1">
                  {detail.user.is_superuser && <Badge color="purple">Superuser</Badge>}
                  {detail.user.is_staff && !detail.user.is_superuser && <Badge color="blue">Admin</Badge>}
                  <Badge color={detail.user.is_active ? 'green' : 'red'}>{detail.user.is_active ? 'Active' : 'Disabled'}</Badge>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Documents', value: detail.stats.documents, icon: FileText },
                { label: 'Sessions', value: detail.stats.sessions, icon: MessagesSquare },
                { label: 'Queries', value: detail.stats.queries, icon: MessageSquare },
              ].map(({ label, value, icon: Icon }) => (
                <div key={label} className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-3 text-center">
                  <Icon size={16} className="mx-auto mb-1 text-zinc-500" />
                  <p className="text-xl font-bold text-white">{value}</p>
                  <p className="text-xs text-zinc-500">{label}</p>
                </div>
              ))}
            </div>

            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-zinc-500">Joined</span><span className="text-zinc-200">{fmt(detail.user.date_joined)}</span></div>
              <div className="flex justify-between"><span className="text-zinc-500">Last login</span><span className="text-zinc-200">{fmtTime(detail.user.last_login)}</span></div>
            </div>

            <div className="space-y-2 border-t border-white/[0.06] pt-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Actions</p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  className={`flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    detail.user.is_active ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20' : 'bg-success-500/10 text-success-400 hover:bg-success-500/20'
                  }`}
                  onClick={() => {
                    const newVal = !detail.user.is_active
                    toggle('is_active', newVal)
                    setDetail(d => ({ ...d, user: { ...d.user, is_active: newVal } }))
                  }}
                >
                  {detail.user.is_active ? <><UserX size={14} /> Disable</> : <><UserCheck size={14} /> Enable</>}
                </button>
                <button
                  className={`flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    detail.user.is_staff ? 'bg-white/5 text-zinc-300 hover:bg-white/10' : 'bg-accent-500/10 text-accent-300 hover:bg-accent-500/20'
                  }`}
                  onClick={() => {
                    const newVal = !detail.user.is_staff
                    toggle('is_staff', newVal)
                    setDetail(d => ({ ...d, user: { ...d.user, is_staff: newVal } }))
                  }}
                >
                  <Crown size={14} /> {detail.user.is_staff ? 'Remove Admin' : 'Make Admin'}
                </button>
              </div>
            </div>

            {detail.recent_documents?.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">Recent Documents</p>
                <div className="space-y-1">
                  {detail.recent_documents.map(d => (
                    <div key={d.id} className="flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-2 text-sm">
                      <span className="max-w-[200px] truncate text-zinc-300">{d.original_filename}</span>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className="text-xs text-zinc-500">{d.file_size_display}</span>
                        <Badge color={d.status === 'completed' ? 'green' : d.status === 'failed' ? 'red' : 'yellow'}>{d.status}</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </motion.div>
    </div>
  )
}

// ─── Main Admin Page ────────────────────────────────────────────────────────
export default function AdminPage() {
  const { user: me, logout } = useAuth()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('overview')

  const [users, setUsers] = useState([])
  const [userTotal, setUserTotal] = useState(0)
  const [userPage, setUserPage] = useState(1)
  const [userSearch, setUserSearch] = useState('')
  const [userLoading, setUserLoading] = useState(false)
  const [selectedUser, setSelectedUser] = useState(null)

  const [docs, setDocs] = useState([])
  const [docTotal, setDocTotal] = useState(0)
  const [docPage, setDocPage] = useState(1)
  const [docSearch, setDocSearch] = useState('')
  const [docStatus, setDocStatus] = useState('')
  const [docLoading, setDocLoading] = useState(false)

  const [chats, setChats] = useState([])
  const [chatTotal, setChatTotal] = useState(0)
  const [chatPage, setChatPage] = useState(1)
  const [chatSearch, setChatSearch] = useState('')
  const [chatLoading, setChatLoading] = useState(false)

  const PAGE_SIZE = 15

  useEffect(() => {
    adminAPI.getStats().then(r => setStats(r.data.data)).catch(() => toast.error('Failed to load stats.')).finally(() => setLoading(false))
  }, [])

  const loadUsers = useCallback(() => {
    setUserLoading(true)
    adminAPI.getUsers({ page: userPage, page_size: PAGE_SIZE, search: userSearch })
      .then(r => { setUsers(r.data.data || []); setUserTotal(r.data.pagination?.total || 0) })
      .catch(() => toast.error('Failed to load users.'))
      .finally(() => setUserLoading(false))
  }, [userPage, userSearch])

  const loadDocs = useCallback(() => {
    setDocLoading(true)
    adminAPI.getDocuments({ page: docPage, page_size: PAGE_SIZE, status: docStatus, search: docSearch })
      .then(r => { setDocs(r.data.data || []); setDocTotal(r.data.pagination?.total || 0) })
      .catch(() => toast.error('Failed to load documents.'))
      .finally(() => setDocLoading(false))
  }, [docPage, docStatus, docSearch])

  const loadChats = useCallback(() => {
    setChatLoading(true)
    adminAPI.getChats({ page: chatPage, page_size: PAGE_SIZE, search: chatSearch })
      .then(r => { setChats(r.data.data || []); setChatTotal(r.data.pagination?.total || 0) })
      .catch(() => toast.error('Failed to load chats.'))
      .finally(() => setChatLoading(false))
  }, [chatPage, chatSearch])

  useEffect(() => { if (tab === 'users')     loadUsers() }, [tab, loadUsers])
  useEffect(() => { if (tab === 'documents') loadDocs()  }, [tab, loadDocs])
  useEffect(() => { if (tab === 'chats')     loadChats() }, [tab, loadChats])

  useEffect(() => setUserPage(1), [userSearch])
  useEffect(() => setDocPage(1),  [docSearch, docStatus])
  useEffect(() => setChatPage(1), [chatSearch])

  const toggleActive = async (userId, current) => {
    try {
      await adminAPI.updateUser(userId, { is_active: !current })
      setUsers(u => u.map(x => x.id === userId ? { ...x, is_active: !current } : x))
      toast.success(current ? 'User disabled.' : 'User enabled.')
    } catch { toast.error('Update failed.') }
  }

  const deleteUser = async (userId, username) => {
    const isSelf = me?.id === userId
    const msg = isSelf
      ? `Delete your own account "${username}" and all its data? You will be signed out. This cannot be undone.`
      : `Delete user "${username}" and all their data? This cannot be undone.`
    if (!confirm(msg)) return
    try {
      await adminAPI.deleteUser(userId)
      if (isSelf) {
        toast.success('Your account has been deleted.')
        await logout() // clears the session; route guards redirect to /login
        return
      }
      setUsers(u => u.filter(x => x.id !== userId)); setUserTotal(t => t - 1)
      toast.success('User deleted.')
    } catch { toast.error('Delete failed.') }
  }

  const deleteDoc = async (docId, name) => {
    if (!confirm(`Delete document "${name}"? This cannot be undone.`)) return
    try {
      await adminAPI.deleteDocument(docId)
      setDocs(d => d.filter(x => x.id !== docId)); setDocTotal(t => t - 1)
      toast.success('Document deleted.')
    } catch { toast.error('Delete failed.') }
  }

  const deleteChat = async (chatId, title) => {
    if (!confirm(`Delete chat "${title}"? This cannot be undone.`)) return
    try {
      await adminAPI.deleteChat(chatId)
      setChats(c => c.filter(x => x.id !== chatId)); setChatTotal(t => t - 1)
      toast.success('Chat deleted.')
    } catch { toast.error('Delete failed.') }
  }

  if (loading) return <PageLoader label="Loading admin console" />

  const tabs = [
    { key: 'overview',  label: 'Overview', icon: ShieldCheck },
    { key: 'users',     label: `Users (${stats?.users.total ?? 0})`, icon: Users },
    { key: 'documents', label: `Documents (${stats?.documents.total ?? 0})`, icon: FileText },
    { key: 'chats',     label: `Chats (${stats?.chat.total_sessions ?? 0})`, icon: MessagesSquare },
  ]

  const docStatusColor = s => s === 'completed' ? 'green' : s === 'failed' ? 'red' : s === 'processing' ? 'blue' : 'yellow'
  const cellTh = 'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500 whitespace-nowrap'

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-accent-600 shadow-glow-sm">
          <ShieldCheck size={20} className="text-white" />
        </div>
        <div>
          <h1 className="font-display text-xl font-bold text-white">Admin Console</h1>
          <p className="text-sm text-zinc-500">System-wide monitoring &amp; management</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-white/[0.06]">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`relative -mb-px flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors ${
              tab === t.key ? 'text-primary-300' : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <t.icon size={14} /> {t.label}
            {tab === t.key && <motion.span layoutId="admin-tab" className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-gradient-to-r from-primary-500 to-accent-500" />}
          </button>
        ))}
      </div>

      {/* OVERVIEW */}
      {tab === 'overview' && stats && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard label="Total Users"     value={stats.users.total}         icon={Users}          gradient="bg-gradient-to-br from-accent-500 to-blue-600"   sub={`${stats.users.active} active`} />
            <StatCard label="Total Documents" value={stats.documents.total}     icon={FileText}       gradient="bg-gradient-to-br from-primary-500 to-violet-600" sub={`${stats.documents.completed} completed`} />
            <StatCard label="Queries (30d)"   value={stats.chat.queries_30d}    icon={MessageSquare}  gradient="bg-gradient-to-br from-success-500 to-teal-600"  sub={`${stats.chat.queries_7d} this week`} />
            <StatCard label="Chat Sessions"   value={stats.chat.total_sessions} icon={MessagesSquare} gradient="bg-gradient-to-br from-orange-500 to-rose-500"   sub={`${stats.chat.total_messages} messages`} />
          </div>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <GlassCard className="p-5">
              <h3 className="mb-4 text-sm font-semibold text-white">Daily Active Users (7 days)</h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={stats.dau_trend} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#71717a' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: '#71717a' }} allowDecimals={false} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: 'rgba(139,92,246,0.08)' }} contentStyle={{ background: '#0d1424', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, fontSize: 12 }} formatter={v => [v, 'Active Users']} />
                  <Bar dataKey="users" fill="#8b5cf6" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </GlassCard>

            <GlassCard className="p-5">
              <h3 className="mb-4 text-sm font-semibold text-white">Queries per Day (7 days)</h3>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={stats.query_trend} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#71717a' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: '#71717a' }} allowDecimals={false} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ background: '#0d1424', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, fontSize: 12 }} formatter={v => [v, 'Queries']} />
                  <Line type="monotone" dataKey="queries" stroke="#10b981" strokeWidth={2} dot={{ r: 3, fill: '#10b981' }} />
                </LineChart>
              </ResponsiveContainer>
            </GlassCard>
          </div>

          <GlassCard className="p-5">
            <h3 className="mb-4 text-sm font-semibold text-white">System Health</h3>
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
              {[
                { label: 'Active Users',   value: stats.users.active,        total: stats.users.total,     color: 'from-accent-500 to-blue-500' },
                { label: 'Admin Users',    value: stats.users.admins,        total: stats.users.total,     color: 'from-primary-500 to-violet-500' },
                { label: 'Processed Docs', value: stats.documents.completed, total: stats.documents.total, color: 'from-success-500 to-teal-500' },
                { label: 'Failed Docs',    value: stats.documents.failed,    total: stats.documents.total, color: 'from-red-500 to-rose-500' },
                { label: 'Pending Docs',   value: stats.documents.pending,   total: stats.documents.total, color: 'from-amber-500 to-yellow-500' },
                { label: 'New Users (7d)', value: stats.users.new_7d,        total: stats.users.total,     color: 'from-orange-500 to-rose-500' },
              ].map(({ label, value, total, color }) => (
                <div key={label}>
                  <div className="mb-1.5 flex justify-between text-xs">
                    <span className="text-zinc-400">{label}</span>
                    <span className="font-semibold text-white">{value} / {total}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                    <motion.div
                      className={`h-full rounded-full bg-gradient-to-r ${color}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${total ? Math.min((value / total) * 100, 100) : 0}%` }}
                      transition={{ duration: 0.8, ease: 'easeOut' }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </GlassCard>
        </motion.div>
      )}

      {/* USERS */}
      {tab === 'users' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <SearchBar value={userSearch} onChange={setUserSearch} placeholder="Search username or email…" />
            <button onClick={loadUsers} className="flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-300"><RefreshCw size={13} /> Refresh</button>
          </div>
          <GlassCard className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-white/[0.06] bg-white/[0.02]">
                  <tr>{['User', 'Email', 'Role', 'Docs', 'Queries', 'Joined', 'Last Login', 'Status', 'Actions'].map(h => <th key={h} className={cellTh}>{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {userLoading ? (
                    <tr><td colSpan={9} className="py-8 text-center text-sm text-zinc-500">Loading…</td></tr>
                  ) : users.length === 0 ? (
                    <tr><td colSpan={9} className="py-8 text-center text-sm text-zinc-500">No users found.</td></tr>
                  ) : users.map(u => (
                    <tr key={u.id} className="transition-colors hover:bg-white/[0.02]">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-accent-600 text-xs font-bold text-white">{u.username[0].toUpperCase()}</div>
                          <span className="whitespace-nowrap font-medium text-white">{u.username}</span>
                        </div>
                      </td>
                      <td className="max-w-[160px] truncate px-4 py-3 text-zinc-400">{u.email || '—'}</td>
                      <td className="px-4 py-3">{u.is_superuser ? <Badge color="purple">Superuser</Badge> : u.is_staff ? <Badge color="blue">Admin</Badge> : <Badge color="gray">User</Badge>}</td>
                      <td className="px-4 py-3 text-zinc-400">{u.documents}</td>
                      <td className="px-4 py-3 text-zinc-400">{u.queries}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-400">{fmt(u.date_joined)}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-400">{fmtTime(u.last_login)}</td>
                      <td className="px-4 py-3"><Badge color={u.is_active ? 'green' : 'red'}>{u.is_active ? 'Active' : 'Disabled'}</Badge></td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button onClick={() => setSelectedUser(u)} className="rounded-lg p-1.5 text-zinc-400 hover:bg-white/5 hover:text-white" title="View details"><Eye size={14} /></button>
                          <button onClick={() => toggleActive(u.id, u.is_active)} className="rounded-lg p-1.5 text-zinc-400 hover:bg-white/5" title={u.is_active ? 'Disable' : 'Enable'}>
                            {u.is_active ? <ToggleRight size={16} className="text-success-400" /> : <ToggleLeft size={16} />}
                          </button>
                          <button onClick={() => deleteUser(u.id, u.username)} className="rounded-lg p-1.5 text-red-400 hover:bg-red-500/10" title="Delete"><Trash2 size={14} /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={userPage} total={userTotal} pageSize={PAGE_SIZE} onChange={setUserPage} />
          </GlassCard>
        </motion.div>
      )}

      {/* DOCUMENTS */}
      {tab === 'documents' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <SearchBar value={docSearch} onChange={setDocSearch} placeholder="Search by filename…" />
              <select className="input-field w-40 py-2 text-sm" value={docStatus} onChange={e => setDocStatus(e.target.value)}>
                <option value="" className="bg-ink-850">All statuses</option>
                <option value="completed" className="bg-ink-850">Completed</option>
                <option value="processing" className="bg-ink-850">Processing</option>
                <option value="pending" className="bg-ink-850">Pending</option>
                <option value="failed" className="bg-ink-850">Failed</option>
              </select>
            </div>
            <button onClick={loadDocs} className="flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-300"><RefreshCw size={13} /> Refresh</button>
          </div>
          <GlassCard className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-white/[0.06] bg-white/[0.02]">
                  <tr>{['Filename', 'Owner', 'Size', 'Pages', 'Chunks', 'Status', 'Uploaded', 'Actions'].map(h => <th key={h} className={cellTh}>{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {docLoading ? (
                    <tr><td colSpan={8} className="py-8 text-center text-sm text-zinc-500">Loading…</td></tr>
                  ) : docs.length === 0 ? (
                    <tr><td colSpan={8} className="py-8 text-center text-sm text-zinc-500">No documents found.</td></tr>
                  ) : docs.map(d => (
                    <tr key={d.id} className="transition-colors hover:bg-white/[0.02]">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <FileText size={14} className="shrink-0 text-zinc-500" />
                          <span className="max-w-[200px] truncate font-medium text-white">{d.original_filename}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-zinc-400">{d.username}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-zinc-400">{d.file_size_display}</td>
                      <td className="px-4 py-3 text-zinc-400">{d.page_count ?? '—'}</td>
                      <td className="px-4 py-3 text-zinc-400">{d.chunk_count ?? '—'}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          {d.status === 'completed'  && <CheckCircle size={13} className="text-success-400" />}
                          {d.status === 'failed'     && <XCircle size={13} className="text-red-400" />}
                          {d.status === 'processing' && <RefreshCw size={13} className="animate-spin text-accent-300" />}
                          {d.status === 'pending'    && <Clock size={13} className="text-amber-400" />}
                          <Badge color={docStatusColor(d.status)}>{d.status}</Badge>
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-400">{fmt(d.created_at)}</td>
                      <td className="px-4 py-3">
                        <button onClick={() => deleteDoc(d.id, d.original_filename)} className="rounded-lg p-1.5 text-red-400 hover:bg-red-500/10" title="Delete"><Trash2 size={14} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={docPage} total={docTotal} pageSize={PAGE_SIZE} onChange={setDocPage} />
          </GlassCard>
        </motion.div>
      )}

      {/* CHATS */}
      {tab === 'chats' && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <SearchBar value={chatSearch} onChange={setChatSearch} placeholder="Search by chat title…" />
            <button onClick={loadChats} className="flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-300"><RefreshCw size={13} /> Refresh</button>
          </div>
          <GlassCard className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-white/[0.06] bg-white/[0.02]">
                  <tr>{['Title', 'Owner', 'Messages', 'Documents', 'Created', 'Last Active', 'Actions'].map(h => <th key={h} className={cellTh}>{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {chatLoading ? (
                    <tr><td colSpan={7} className="py-8 text-center text-sm text-zinc-500">Loading…</td></tr>
                  ) : chats.length === 0 ? (
                    <tr><td colSpan={7} className="py-8 text-center text-sm text-zinc-500">No chats found.</td></tr>
                  ) : chats.map(c => (
                    <tr key={c.id} className="transition-colors hover:bg-white/[0.02]">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <MessagesSquare size={14} className="shrink-0 text-zinc-500" />
                          <span className="max-w-[200px] truncate font-medium text-white">{c.title}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-zinc-400">{c.username}</td>
                      <td className="px-4 py-3 text-zinc-400">{c.message_count ?? 0}</td>
                      <td className="max-w-[160px] truncate px-4 py-3 text-xs text-zinc-400">{c.document_names?.join(', ') || '—'}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-400">{fmt(c.created_at)}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-zinc-400">{fmtTime(c.updated_at)}</td>
                      <td className="px-4 py-3">
                        <button onClick={() => deleteChat(c.id, c.title)} className="rounded-lg p-1.5 text-red-400 hover:bg-red-500/10" title="Delete"><Trash2 size={14} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={chatPage} total={chatTotal} pageSize={PAGE_SIZE} onChange={setChatPage} />
          </GlassCard>
        </motion.div>
      )}

      {selectedUser && (
        <UserModal user={selectedUser} onClose={() => setSelectedUser(null)} onUpdate={(id, patch) => setUsers(u => u.map(x => x.id === id ? { ...x, ...patch } : x))} />
      )}
    </div>
  )
}
