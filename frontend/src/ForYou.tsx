import { useEffect, useState } from 'react'
import { ArrowRight, CalendarDays, Check, ChevronDown, Flower2, Link2, LoaderCircle, MessageCircle, RotateCcw, X } from 'lucide-react'
import { api } from './api'

type Source = { id: number; person_id: number; person: string; note_id: number; note_revision?: number; category: string; value: string; evidence: string; edited: number }
type Kind = 'follow_up' | 'date' | 'connection'
type Suggestion = { id: string; kind: Kind; title: string; why: string; sources: Source[]; due_start: string | null; due_end: string | null; overdue: boolean; status: 'open' | 'done' | 'dismissed' }
type Feed = { suggestions: Suggestion[]; today: string; timezone: string }
const labels: Record<Kind, string> = { follow_up: 'Follow-up', date: 'Coming up', connection: 'Possible connection' }
const icons = { follow_up: MessageCircle, date: CalendarDays, connection: Link2 }
const filters: { value: Kind | 'all'; label: string }[] = [
  { value: 'all', label: 'All' }, { value: 'follow_up', label: 'Follow-ups' },
  { value: 'date', label: 'Dates' }, { value: 'connection', label: 'Connections' },
]
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York'
const endpoint = `/for-you?timezone=${encodeURIComponent(timezone)}`

function dateLabel(item: Suggestion, today: string) {
  if (!item.due_start) return null
  // Noon avoids moving a date-only value to the prior day in western timezones.
  const format = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  if (item.due_start !== item.due_end) return `${format(item.due_start)} – ${format(item.due_end!)}`
  if (item.due_start === today) return 'Today'
  return format(item.due_start)
}

export default function ForYou({ revision, onSource, onPerson, onAddNote, compact = false }: {
  compact?: boolean; revision: unknown; onSource: (noteId: number, revision?: number) => void; onPerson: (personId: number) => void; onAddNote: () => void
}) {
  const [feed, setFeed] = useState<Feed | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState<Kind | 'all'>('all')
  const [limit, setLimit] = useState(6)
  const [status, setStatus] = useState('')
  const load = async () => { const result = await api<Feed>(endpoint); setFeed(result); setError('') }
  useEffect(() => {
    let cancelled = false
    const refresh = () => api<Feed>(endpoint).then(result => { if (!cancelled) { setFeed(result); setError('') } }).catch(err => { if (!cancelled) setError(err.message) })
    void refresh()
    // Refresh dates after midnight and after returning to an open browser tab.
    const timer = window.setInterval(refresh, 60000)
    window.addEventListener('focus', refresh)
    return () => { cancelled = true; window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [revision])
  const act = async (item: Suggestion, nextStatus: Suggestion['status']) => {
    setBusy(true); setError('')
    try {
      await api(`/for-you/${item.id}?timezone=${encodeURIComponent(timezone)}`, 'PATCH', { status: nextStatus })
      await load()
      setStatus(nextStatus === 'done' ? 'Marked done.' : nextStatus === 'dismissed' ? 'Suggestion dismissed.' : 'Suggestion restored.')
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  const active = feed?.suggestions.filter(item => item.status === 'open') || []
  const shown = active.filter(item => filter === 'all' || item.kind === filter)
  const past = feed?.suggestions.filter(item => item.status !== 'open') || []

  const Title = compact ? 'h3' : 'h2'
  return <section className={`for-you-content ${compact ? 'for-you-compact' : ''}`} aria-label="Personal suggestions">
    {error && <div className="alert error" role="alert"><span>{error}</span><button className="text-button" onClick={() => load().catch(err => setError(err.message))}>Retry</button></div>}
    <p className="sr-only" role="status">{status}</p>
    {!feed && !error && <div className="loading-state"><LoaderCircle className="spin" size={20} /> Gathering the details…</div>}
    {feed && <>
      {active.length > 0 && <div className="feed-filters" role="group" aria-label="Filter suggestions">{filters.map(option => <button key={option.value} aria-pressed={filter === option.value} onClick={() => { setFilter(option.value); setLimit(6) }}>{option.label}</button>)}</div>}
      {!shown.length && <div className="feed-empty"><Flower2 size={36} strokeWidth={1.2} /><h2>{active.length ? 'Nothing in this view just yet.' : past.length ? 'A little room to breathe.' : 'A little attention starts here.'}</h2><p>{active.length ? 'Try another filter to see your other suggestions.' : past.length ? 'You’ve handled the current suggestions. New notes and upcoming dates will bring more.' : 'As your notes grow, promises, upcoming dates, and possible connections will find their way here.'}</p>{!active.length && <button className="text-button" onClick={onAddNote}>Add a note <ArrowRight size={15} /></button>}</div>}
      <div className="suggestion-list">{shown.slice(0, compact ? shown.length : limit).map(item => {
        const Icon = icons[item.kind]
        const due = dateLabel(item, feed.today)
        return <article key={item.id} className="suggestion-card">
          <div className="suggestion-meta"><span><Icon size={14} /> {labels[item.kind]}</span>{due && <span className={item.overdue ? 'overdue' : 'suggestion-date'}>{item.overdue ? 'Date passed · ' : ''}{due}</span>}</div>
          <Title>{item.title}</Title>
          <div className="suggestion-facts">{item.sources.map((source, index) => <p key={`${source.id}-${index}`}>{item.kind === 'connection' && <strong>{source.person}: </strong>}{source.value}</p>)}</div>
          <p className="suggestion-why">{item.why}</p>
          <details className="suggestion-sources"><summary>Why this appeared <ChevronDown size={13} /></summary>{item.sources.map((source, index) => <div key={`${source.id}-${index}`}><button className="source-link" onClick={() => onPerson(source.person_id)}>{source.person}</button><blockquote>“{source.evidence}”</blockquote><button className="source-link" onClick={() => onSource(source.note_id, source.note_revision)}>Read source note <ArrowRight size={12} /></button>{!!source.edited && <span className="edited-label">Memory edited by you</span>}</div>)}</details>
          <div className="suggestion-actions"><button className="small-button" disabled={busy} onClick={() => act(item, 'done')}><Check size={13} /> Mark done</button><button className="text-button" disabled={busy} onClick={() => act(item, 'dismissed')}><X size={13} /> Dismiss</button></div>
        </article>
      })}</div>
      {!compact && shown.length > limit && <button className="text-button feed-more" onClick={() => setLimit(value => value + 6)}>Show more <ChevronDown size={14} /></button>}
      {past.length > 0 && <details className="suggestion-history"><summary>Done & dismissed <span>{past.length}</span></summary>{past.map(item => <div key={item.id}><div><strong>{item.title}</strong><small>{item.status === 'done' ? 'Done' : 'Dismissed'}</small></div><button className="text-button" disabled={busy} onClick={() => act(item, 'open')}><RotateCcw size={12} /> Restore</button></div>)}</details>}
    </>}
  </section>
}
