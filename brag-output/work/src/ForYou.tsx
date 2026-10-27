import { useEffect, useState } from 'react'
import { ArrowRight, CalendarDays, Check, ChevronDown, Flower2, Link2, LoaderCircle, MessageCircle, RotateCcw, X } from 'lucide-react'
import { api } from './api'

type Source = { id: number; person_id: number | null; person: string; note_id: number; note_revision?: number; category: string; value: string; evidence: string; edited: number }
type Kind = 'follow_up' | 'date' | 'connection'
type Scope = 'all' | 'personal' | 'others'
type Suggestion = { id: string; scope: Exclude<Scope, 'all'>; category?: string; kind: Kind; title: string; why: string; sources: Source[]; completion?: {note_id: number; note_revision: number; evidence: string}; due_start: string | null; due_end: string | null; overdue: boolean; status: 'open' | 'done' | 'dismissed' }
type Feed = { suggestions: Suggestion[]; today: string; timezone: string }
const labels: Record<Kind, string> = { follow_up: 'Follow-up', date: 'Coming up', connection: 'Possible connection' }
const icons = { follow_up: MessageCircle, date: CalendarDays, connection: Link2 }
const filters: { value: Kind | 'all'; label: string }[] = [
  { value: 'all', label: 'All types' }, { value: 'follow_up', label: 'Follow-ups' },
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

export default function ForYou({ revision, onSource, onPerson, onAddNote, compact = false, profile = false, fixedScope, personId }: {
  compact?: boolean; profile?: boolean; fixedScope?: 'personal' | 'others'; personId?: number;
  revision: unknown; onSource: (noteId: number, revision?: number) => void; onPerson: (personId: number) => void; onAddNote: () => void
}) {
  const [feed, setFeed] = useState<Feed | null>((window as any).__film.feed)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState<Kind | 'all'>('all')
  const [scope, setScope] = useState<Scope>('all')
  const [limit, setLimit] = useState(6)
  const [status, setStatus] = useState('')
  const query = `${endpoint}${personId ? '&include_all_plans=true' : ''}`
  const load = async () => { const result = await api<Feed>(query); setFeed(result); setError('') }
  useEffect(() => {
    let cancelled = false
    const refresh = () => api<Feed>(query).then(result => { if (!cancelled) { setFeed(result); setError('') } }).catch(err => { if (!cancelled) setError(err.message) })
    void refresh()
    // Refresh dates after midnight and after returning to an open browser tab.
    const timer = window.setInterval(refresh, 60000)
    window.addEventListener('focus', refresh)
    return () => { cancelled = true; window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [revision, query])
  const act = async (item: Suggestion, nextStatus: Suggestion['status']) => {
    setBusy(true); setError('')
    try {
      await api(`/for-you/${item.id}?timezone=${encodeURIComponent(timezone)}${personId ? '&include_all_plans=true' : ''}`, 'PATCH', { status: nextStatus })
      await load()
      setStatus(nextStatus === 'done' ? 'Marked done.' : nextStatus === 'dismissed' ? 'Suggestion dismissed.' : 'Suggestion restored.')
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  const relevant = feed?.suggestions.filter(item => (!fixedScope || item.scope === fixedScope) && (!personId || item.kind !== 'connection' && item.sources.some(source => source.person_id === personId && ['plan', 'commitment'].includes(source.category)))) || []
  const active = relevant.filter(item => item.status === 'open')
  const matches = (item: Suggestion) => (!!fixedScope || scope === 'all' || item.scope === scope) && (filter === 'all' || item.kind === filter)
  const shown = active.filter(matches)
  const past = relevant.filter(item => item.status !== 'open' && matches(item))
  const bucket = (item: Suggestion) => item.overdue ? 0 : item.due_start ? 1 : 2
  if (profile) shown.sort((a, b) => bucket(a) - bucket(b) || (a.due_start || '').localeCompare(b.due_start || ''))
  const visible = shown.slice(0, compact || profile ? shown.length : limit)

  const Title = compact ? 'h3' : 'h2'
  return <section className={`for-you-content ${compact ? 'for-you-compact' : ''} ${profile ? 'profile-tasks' : ''}`} aria-label={profile ? 'Tasks and obligations' : 'Personal suggestions'}>
    {error && <div className="alert error" role="alert"><span>{error}</span><button className="text-button" onClick={() => load().catch(err => setError(err.message))}>Retry</button></div>}
    <p className="sr-only" role="status">{status}</p>
    {!feed && !error && <div className="loading-state"><LoaderCircle className="spin" size={20} /> Gathering the details…</div>}
    {feed && <>
      {!fixedScope && <div className="feed-filters feed-scope-filters" role="group" aria-label="Filter by who suggestions involve">{(['all', 'personal', 'others'] as Scope[]).map(value => <button key={value} aria-pressed={scope === value} onClick={() => { setScope(value); setLimit(6) }}>{value === 'all' ? 'All' : value === 'personal' ? 'Personal' : 'Others'}</button>)}</div>}
      {!profile && active.length > 0 && <div className="feed-filters" role="group" aria-label="Filter suggestions">{filters.map(option => <button key={option.value} aria-pressed={filter === option.value} onClick={() => { setFilter(option.value); setLimit(6) }}>{option.label}</button>)}</div>}
      {!shown.length && (profile ? <p className="profile-tasks-empty">{past.length ? 'All caught up.' : fixedScope === 'personal' ? 'Your tasks, reminders, and goals will gather here as you write.' : 'No tasks or follow-ups recorded yet.'}</p> : <div className="feed-empty"><Flower2 size={36} strokeWidth={1.2} /><h2>{active.length ? 'Nothing in this view just yet.' : past.length ? 'A little room to breathe.' : 'A little attention starts here.'}</h2><p>{active.length ? 'Try another filter to see your other suggestions.' : scope === 'personal' ? 'Your own tasks, plans, reminders, and goals will appear here as you write.' : past.length ? 'You’ve handled the current suggestions. New notes and upcoming dates will bring more.' : 'As your notes grow, promises, upcoming dates, and possible connections will find their way here.'}</p>{!active.length && <button className="text-button" onClick={onAddNote}>Add a note <ArrowRight size={15} /></button>}</div>)}
      <div className="suggestion-list" tabIndex={profile ? 0 : undefined} aria-label={profile ? 'Scrollable tasks and obligations' : undefined}>{visible.map((item, itemIndex) => {
        const Icon = icons[item.kind]
        const due = dateLabel(item, feed.today)
        if (profile) return <div key={item.id}>
          <h4 className={`task-group-label ${itemIndex > 0 && bucket(visible[itemIndex - 1]) === bucket(item) ? 'task-group-continuation' : ''}`}>{['Date passed', 'Upcoming', 'Anytime'][bucket(item)]}</h4>
          <article className="profile-task-row">
            <div className="profile-task-writing"><p tabIndex={0}>{item.sources[0].value}</p><div className="profile-task-meta">{due && <span>{due}</span>}{item.scope === 'personal' && <span>{item.category}</span>}<button className="source-link" onClick={() => onSource(item.sources[0].note_id, item.sources[0].note_revision)}>Source <ArrowRight size={10} /></button></div></div>
            <div className="profile-task-actions"><button className="icon-button" aria-label={`Mark done: ${item.sources[0].value}`} title="Mark done" disabled={busy} onClick={() => act(item, 'done')}><Check size={14} /></button><button className="icon-button" aria-label={`Dismiss: ${item.sources[0].value}`} title="Dismiss" disabled={busy} onClick={() => act(item, 'dismissed')}><X size={14} /></button></div>
          </article>
        </div>
        return <article key={item.id} className="suggestion-card">
          <div className="suggestion-meta"><span><Icon size={14} /> {item.scope === 'personal' ? `Personal · ${item.category === 'goal' ? 'Goal' : labels[item.kind]}` : labels[item.kind]}</span>{due && <span className={item.overdue ? 'overdue' : 'suggestion-date'}>{item.overdue ? 'Date passed · ' : ''}{due}</span>}</div>
          <Title>{item.title}</Title>
          <div className="suggestion-facts">{item.sources.map((source, index) => <p key={`${source.id}-${index}`}>{item.kind === 'connection' && <strong>{source.person}: </strong>}{source.value}</p>)}</div>
          <p className="suggestion-why">{item.why}</p>
          <details className="suggestion-sources"><summary>Why this appeared <ChevronDown size={13} /></summary>{item.sources.map((source, index) => <div key={`${source.id}-${index}`}>{source.person_id !== null ? <button className="source-link" onClick={() => onPerson(source.person_id!)}>{source.person}</button> : <span className="source-link">From your writing</span>}<blockquote>“{source.evidence}”</blockquote><button className="source-link" onClick={() => onSource(source.note_id, source.note_revision)}>Read source note <ArrowRight size={12} /></button>{!!source.edited && <span className="edited-label">Memory edited by you</span>}</div>)}</details>
          <div className="suggestion-actions"><button className="small-button" disabled={busy} onClick={() => act(item, 'done')}><Check size={13} /> Mark done</button><button className="text-button" disabled={busy} onClick={() => act(item, 'dismissed')}><X size={13} /> Dismiss</button></div>
        </article>
      })}</div>
      {!compact && !profile && shown.length > limit && <button className="text-button feed-more" onClick={() => setLimit(value => value + 6)}>Show more <ChevronDown size={14} /></button>}
      {past.length > 0 && <details className="suggestion-history"><summary>Done & dismissed <span>{past.length}</span></summary>{past.map(item => <div key={item.id}><div><strong>{profile || item.scope === 'personal' ? item.sources[0].value : item.title}</strong><small>{item.status === 'done' ? item.completion ? 'Done from your writing' : 'Done' : 'Dismissed'}</small>{item.completion && <button className="source-link completion-source" title={item.completion.evidence} onClick={() => onSource(item.completion!.note_id, item.completion!.note_revision)}>Completion source <ArrowRight size={10} /></button>}</div><button className="text-button" disabled={busy} onClick={() => act(item, 'open')}><RotateCcw size={12} /> Restore</button></div>)}</details>}
    </>}
  </section>
}
