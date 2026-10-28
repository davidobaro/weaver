import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowRight, CalendarDays, Check, ChevronDown, Clock3, Flower2, Link2, LoaderCircle, MessageCircle, Repeat2, RotateCcw, SkipForward, X } from 'lucide-react'
import { api } from './api'
import { suggestionDigest } from './suggestionDigest'

type Source = { id: number; person_id: number | null; person: string; note_id: number; note_revision?: number; category: string; value: string; evidence: string; edited: number }
type Kind = 'follow_up' | 'date' | 'connection'
type Scope = 'all' | 'personal' | 'others'
type Suggestion = { id: string; repeat: Repeat | null; repeat_origin: 'writing' | 'manual' | null; past_occurrence: boolean; scope: Exclude<Scope, 'all'>; category?: string; kind: Kind; title: string; why: string; sources: Source[]; completion?: {note_id: number; note_revision: number; evidence: string}; due_start: string | null; due_end: string | null; original_due_start: string | null; original_due_end: string | null; due_date_overridden: boolean; can_schedule: boolean; snoozed_until: string | null; snoozed: boolean; overdue: boolean; status: 'open' | 'done' | 'dismissed' }
type Repeat = 'daily' | 'weekly' | 'monthly'
type Mode = 'due' | 'snooze' | 'repeat'
type RepeatPatch = {frequency: Repeat | null; start_date: string | null}
type TimingPatch = { due_date?: string | null; reset_due_date?: boolean; snoozed_until?: string | null }
type Feed = { suggestions: Suggestion[]; today: string; timezone: string }
const labels: Record<Kind, string> = { follow_up: 'Follow-up', date: 'Coming up', connection: 'Possible connection' }
const icons = { follow_up: MessageCircle, date: CalendarDays, connection: Link2 }
const filters: { value: Kind | 'all'; label: string }[] = [
  { value: 'all', label: 'All types' }, { value: 'follow_up', label: 'Follow-ups' },
  { value: 'date', label: 'Dates' }, { value: 'connection', label: 'Connections' },
]
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York'
const endpoint = `/for-you?timezone=${encodeURIComponent(timezone)}`
const changeEvent = 'weaver-suggestions-changed'
const changeKey = 'weaver-suggestions-revision'

function afterDays(today: string, days: number) {
  const date = new Date(`${today}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

function dateLabel(item: Suggestion, today: string) {
  if (!item.due_start) return null
  // Noon avoids moving a date-only value to the prior day in western timezones.
  const format = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', ...(value.slice(0, 4) !== today.slice(0, 4) ? {year: 'numeric'} as const : {}) })
  if (item.due_start !== item.due_end) return `${format(item.due_start)} – ${format(item.due_end!)}`
  if (item.due_start === today) return 'Today'
  return format(item.due_start)
}

export default function ForYou({ revision, onSource, onPerson, onAddNote, compact = false, profile = false, fixedScope, personId, onOpenAll }: {
  onOpenAll?: () => void; compact?: boolean; profile?: boolean; fixedScope?: 'personal' | 'others'; personId?: number;
  revision: unknown; onSource: (noteId: number, revision?: number) => void; onPerson: (personId: number) => void; onAddNote: () => void
}) {
  const [feed, setFeed] = useState<Feed | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState<Kind | 'all'>('all')
  const [scope, setScope] = useState<Scope>('all')
  const [status, setStatus] = useState('')
  const [editing, setEditing] = useState<{item: Suggestion; mode: Mode} | null>(null)
  const instance = useId()
  const request = useRef(0)
  const query = `${endpoint}${personId ? '&include_all_plans=true' : ''}`
  const load = async () => { const seq = ++request.current; const result = await api<Feed>(query); if (seq === request.current) { setFeed(result); setError('') } }
  const announceChange = () => {
    window.dispatchEvent(new CustomEvent(changeEvent, {detail: instance}))
    try { localStorage.setItem(changeKey, `${Date.now()}-${instance}`) } catch { /* The refresh timer still works without browser storage. */ }
  }
  useEffect(() => {
    let cancelled = false
    const refresh = () => { const seq = ++request.current; return api<Feed>(query).then(result => { if (!cancelled && seq === request.current) { setFeed(result); setError('') } }).catch(err => { if (!cancelled && seq === request.current) setError(err.message) }) }
    const changed = (event: Event) => { if ((event as CustomEvent).detail !== instance) void refresh() }
    const stored = (event: StorageEvent) => { if (event.key === changeKey) void refresh() }
    void refresh()
    // Refresh dates after midnight and after returning to an open browser tab.
    const timer = window.setInterval(refresh, 60000)
    window.addEventListener('focus', refresh)
    window.addEventListener(changeEvent, changed)
    window.addEventListener('storage', stored)
    return () => { cancelled = true; window.clearInterval(timer); window.removeEventListener('focus', refresh); window.removeEventListener(changeEvent, changed); window.removeEventListener('storage', stored) }
  }, [revision, query, instance])
  const act = async (item: Suggestion, nextStatus: Suggestion['status'], stopRepeat = false) => {
    setBusy(true); setError('')
    try {
      await api(`/for-you/${item.id}?timezone=${encodeURIComponent(timezone)}${personId ? '&include_all_plans=true' : ''}`, 'PATCH', { status: nextStatus, ...(stopRepeat ? {stop_repeat: true} : {}) })
      await load()
      announceChange()
      setStatus(stopRepeat ? 'Repeating reminder dismissed. Repeat turned off.' : item.repeat && !item.past_occurrence && nextStatus !== 'open' ? nextStatus === 'done' ? 'Marked done. Next occurrence scheduled.' : 'Occurrence skipped. Next date scheduled.' : nextStatus === 'done' ? 'Marked done.' : nextStatus === 'dismissed' ? 'Suggestion dismissed.' : 'Suggestion restored.')
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  const dismiss = (item: Suggestion) => act(item, 'dismissed', !!item.repeat && !item.past_occurrence)
  const saveTiming = async (item: Suggestion, patch: TimingPatch | RepeatPatch) => {
    await api(`/for-you/${item.id}/${'frequency' in patch ? 'repeat' : 'timing'}?timezone=${encodeURIComponent(timezone)}`, 'PATCH', patch)
    await load()
    announceChange()
    setStatus('frequency' in patch ? patch.frequency ? 'Repeat schedule saved.' : 'Repeat turned off.' : 'snoozed_until' in patch ? patch.snoozed_until ? 'Snoozed.' : 'Reminder brought back.' : 'Due date updated.')
  }
  const bringBack = async (item: Suggestion) => {
    setBusy(true); setError('')
    try { await saveTiming(item, {snoozed_until: null}) } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  const timingControls = (item: Suggestion) => item.can_schedule && <>
    <button className="icon-button" aria-label={`Set due date: ${item.sources[0].value}`} title="Set due date" disabled={busy} onClick={() => setEditing({item, mode: 'due'})}><CalendarDays size={14} /></button>
    <button className="icon-button" aria-label={`Repeat: ${item.sources[0].value}`} title="Repeat reminder" disabled={busy} onClick={() => setEditing({item, mode: 'repeat'})}><Repeat2 size={14} /></button>
    <button className="icon-button" aria-label={`Snooze: ${item.sources[0].value}`} title="Snooze" disabled={busy} onClick={() => setEditing({item, mode: 'snooze'})}><Clock3 size={14} /></button>
  </>
  const relevant = feed?.suggestions.filter(item => (!fixedScope || item.scope === fixedScope) && (!personId || item.kind !== 'connection' && item.sources.some(source => source.person_id === personId && ['plan', 'commitment'].includes(source.category)))) || []
  const active = relevant.filter(item => item.status === 'open' && !item.snoozed)
  const matches = (item: Suggestion) => (!!fixedScope || scope === 'all' || item.scope === scope) && (filter === 'all' || item.kind === filter)
  const shown = active.filter(matches)
  const past = relevant.filter(item => item.status !== 'open' && matches(item))
  const snoozed = relevant.filter(item => item.status === 'open' && item.snoozed && matches(item))
  const bucket = (item: Suggestion) => item.overdue ? 0 : item.due_start ? 1 : 2
  if (profile) shown.sort((a, b) => bucket(a) - bucket(b) || (a.due_start || '').localeCompare(b.due_start || ''))
  const digest = suggestionDigest(shown, feed?.today || new Date().toISOString().slice(0,10))
  const visible = profile ? shown : digest.highlights

  const Title = compact ? 'h3' : 'h2'
  const renderSuggestion = (item: Suggestion, itemIndex: number) => {
        const Icon = icons[item.kind]
        const due = dateLabel(item, feed!.today)
        if (profile) return <div key={item.id}>
          <h4 className={`task-group-label ${itemIndex > 0 && bucket(visible[itemIndex - 1]) === bucket(item) ? 'task-group-continuation' : ''}`}>{['Date passed', 'Upcoming', 'Anytime'][bucket(item)]}</h4>
          <article className="profile-task-row">
            <div className="profile-task-writing"><p tabIndex={0}>{item.sources[0].value}</p><div className="profile-task-meta">{due && <span>{due}</span>}{item.repeat ? <span className="repeat-label"><Repeat2 size={10} /> {item.past_occurrence ? 'Past occurrence' : item.repeat}</span> : item.scope === 'personal' && <span>{item.category}</span>}<button className="source-link" onClick={() => onSource(item.sources[0].note_id, item.sources[0].note_revision)}>Source <ArrowRight size={10} /></button></div></div>
            <div className="profile-task-actions">{timingControls(item)}<button className="icon-button" aria-label={`Mark done: ${item.sources[0].value}`} title="Mark done" disabled={busy} onClick={() => act(item, 'done')}><Check size={14} /></button><button className="icon-button" aria-label={`${item.repeat && !item.past_occurrence ? 'Dismiss repeating reminder' : 'Dismiss'}: ${item.sources[0].value}`} title={item.repeat && !item.past_occurrence ? 'Dismiss and stop repeating' : 'Dismiss'} disabled={busy} onClick={() => dismiss(item)}><X size={14} /></button></div>
          </article>
        </div>
        return <article key={item.id} className="suggestion-card">
          <div className="suggestion-meta"><span><Icon size={14} /> {item.scope === 'personal' ? `Personal · ${item.category === 'goal' ? 'Goal' : labels[item.kind]}` : labels[item.kind]}</span>{due && <span className={item.overdue ? 'overdue' : 'suggestion-date'}>{item.overdue ? 'Date passed · ' : ''}{due}</span>}</div>
          {item.repeat && <span className="repeat-label"><Repeat2 size={12} /> {item.past_occurrence ? 'Past occurrence' : `Repeats ${item.repeat}`}</span>}
          <Title>{item.kind === 'connection' ? item.title : item.sources[0].value}</Title>
          {item.kind === 'connection' && <div className="suggestion-facts">{item.sources.map((source, index) => <p key={`${source.id}-${index}`}><strong>{source.person}: </strong>{source.value}</p>)}</div>}
          <details className="suggestion-sources"><summary>Why this appeared <ChevronDown size={13} /></summary><p className="suggestion-why">{item.why}</p>{item.sources.map((source, index) => <div key={`${source.id}-${index}`}>{source.person_id !== null ? <button className="source-link" onClick={() => onPerson(source.person_id!)}>{source.person}</button> : <span className="source-link">From your writing</span>}<blockquote>“{source.evidence}”</blockquote><button className="source-link" onClick={() => onSource(source.note_id, source.note_revision)}>Read source note <ArrowRight size={12} /></button>{!!source.edited && <span className="edited-label">Memory edited by you</span>}</div>)}</details>
          <div className="suggestion-actions"><button className="small-button" disabled={busy} onClick={() => act(item, 'done')}><Check size={13} /> Mark done</button><ActionDropdown label={item.sources[0].value} disabled={busy}>
            {item.can_schedule && <>
              <button type="button" onClick={() => setEditing({item, mode: 'due'})}><CalendarDays size={14} /> Set due date</button>
              <button type="button" onClick={() => setEditing({item, mode: 'repeat'})}><Repeat2 size={14} /> {item.repeat ? 'Change repeat' : 'Set repeat'}</button>
              <button type="button" onClick={() => setEditing({item, mode: 'snooze'})}><Clock3 size={14} /> Snooze</button>
            </>}
            {item.repeat && !item.past_occurrence && <button type="button" onClick={() => act(item, 'dismissed')}><SkipForward size={14} /> Skip once</button>}
            <button type="button" className="dropdown-dismiss" onClick={() => dismiss(item)}><X size={14} /> {item.repeat && !item.past_occurrence ? 'Dismiss repeat' : 'Dismiss'}</button>
          </ActionDropdown></div>
        </article>

  }
  return <section className={`for-you-content ${compact ? 'for-you-compact' : ''} ${profile ? 'profile-tasks' : ''}`} aria-label={profile ? 'Tasks and obligations' : 'Personal suggestions'}>
    {error && <div className="alert error" role="alert"><span>{error}</span><button className="text-button" onClick={() => load().catch(err => setError(err.message))}>Retry</button></div>}
    <p className="sr-only" role="status">{status}</p>
    {!feed && !error && <div className="loading-state"><LoaderCircle className="spin" size={20} /> Gathering the details…</div>}
    {feed && <>
      {!fixedScope && <div className="feed-filters feed-scope-filters" role="group" aria-label="Filter by who suggestions involve">{(['all', 'personal', 'others'] as Scope[]).map(value => <button key={value} aria-pressed={scope === value} onClick={() => { setScope(value) }}>{value === 'all' ? 'All' : value === 'personal' ? 'Personal' : 'Others'}</button>)}</div>}
      {!profile && !compact && relevant.some(item => item.status === 'open') && <details className="digest-type-filter"><summary>{filters.find(option=>option.value===filter)?.label}<ChevronDown size={12}/></summary><div className="feed-filters" role="group" aria-label="Filter suggestions">{filters.map(option=><button key={option.value} aria-pressed={filter===option.value} onClick={()=>setFilter(option.value)}>{option.label}</button>)}</div></details>}
      {!shown.length && (snoozed.length ? <p className="profile-tasks-empty">Nothing needs attention in this view right now. Your snoozed reminders are below.</p> : profile ? <p className="profile-tasks-empty">{past.length ? 'All caught up.' : fixedScope === 'personal' ? 'Your tasks, reminders, and goals will gather here as you write.' : 'No tasks or follow-ups recorded yet.'}</p> : <div className="feed-empty"><Flower2 size={36} strokeWidth={1.2} /><h2>{active.length ? 'Nothing in this view just yet.' : past.length ? 'A little room to breathe.' : 'A little attention starts here.'}</h2><p>{active.length ? 'Try another filter to see your other suggestions.' : scope === 'personal' ? 'Your own tasks, plans, reminders, and goals will appear here as you write.' : past.length ? 'You’ve handled the current suggestions. New notes and upcoming dates will bring more.' : 'As your notes grow, promises, upcoming dates, and possible connections will find their way here.'}</p>{!active.length && <button className="text-button" onClick={onAddNote}>Add a note <ArrowRight size={15} /></button>}</div>)}
      {!profile && !visible.length && shown.length > 0 && <p className="digest-quiet">{compact ? 'Nothing coming up in the next two weeks.' : 'Nothing coming up in the next two weeks. Your later reminders are below.'}</p>}
      <div className="suggestion-list" tabIndex={profile ? 0 : undefined} aria-label={profile ? 'Scrollable tasks and obligations' : 'Suggested for now'}>{visible.map(renderSuggestion)}</div>
      {!profile && compact && digest.remaining > 0 && <button className="source-link digest-view-all" onClick={onOpenAll}>View {digest.remaining} more {digest.remaining === 1 ? 'suggestion' : 'suggestions'} <ArrowRight size={12}/></button>}
      {!profile && !compact && digest.groups.map(group=><details key={group.key} className={`digest-group digest-group-${group.key}`}><summary>{group.label}<span>{group.items.length}</span><ChevronDown size={13}/></summary><div className="suggestion-list">{group.items.map(renderSuggestion)}</div></details>)}
      {snoozed.length > 0 && <details className="suggestion-history snoozed-history"><summary>Snoozed <span>{snoozed.length}</span></summary>{snoozed.map(item => <div key={item.id}><div><strong>{item.sources[0].value}</strong><small>Until {dateLabel({...item, due_start: item.snoozed_until, due_end: item.snoozed_until}, feed.today)}</small><button className="source-link" onClick={() => onSource(item.sources[0].note_id, item.sources[0].note_revision)}>Source <ArrowRight size={10} /></button></div><div className="snoozed-actions"><button className="text-button" disabled={busy} onClick={() => bringBack(item)}><RotateCcw size={12} /> Bring back</button>{timingControls(item)}</div></div>)}</details>}
      {past.length > 0 && <details className="suggestion-history"><summary>Done & dismissed <span>{past.length}</span></summary>{past.map(item => <div key={item.id}><div><strong>{profile || item.scope === 'personal' ? item.sources[0].value : item.title}</strong><small>{item.past_occurrence && <>{dateLabel(item, feed.today)} · </>}{item.status === 'done' ? item.completion ? 'Done from your writing' : 'Done' : 'Dismissed'}</small>{item.completion && <button className="source-link completion-source" title={item.completion.evidence} onClick={() => onSource(item.completion!.note_id, item.completion!.note_revision)}>Completion source <ArrowRight size={10} /></button>}</div><button className="text-button" disabled={busy} onClick={() => act(item, 'open')}><RotateCcw size={12} /> Restore</button></div>)}</details>}
    </>}
    {editing && feed && <TimingEditor key={`${editing.item.id}-${editing.mode}`} item={editing.item} mode={editing.mode} today={feed.today} onClose={() => setEditing(null)} onSave={patch => saveTiming(editing.item, patch)} />}
  </section>
}

function TimingEditor({item, mode, today, onClose, onSave}: {item: Suggestion; mode: Mode; today: string; onClose: () => void; onSave: (patch: TimingPatch | RepeatPatch) => Promise<void>}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [repeat, setRepeat] = useState<Repeat | ''>(item.repeat || '')
  const [value, setValue] = useState(mode === 'repeat' ? item.due_start || today : mode === 'due' ? item.due_start || '' : item.snoozed && item.snoozed_until || afterDays(today, 1))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const titleId = useId()
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const element = dialog.current!
    element.showModal()
    return () => { element.close(); previous?.focus() }
  }, [])
  const save = async (patch: TimingPatch | RepeatPatch) => {
    setSaving(true); setError('')
    try { await onSave(patch); onClose() } catch (err) { setError((err as Error).message); setSaving(false) }
  }
  return createPortal(<dialog ref={dialog} className="timing-dialog" aria-labelledby={titleId} onCancel={onClose} onClick={event => { const box = event.currentTarget.getBoundingClientRect(); if (!saving && event.target === event.currentTarget && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) onClose() }}>
    <div className="modal-heading"><h2 id={titleId}>{mode === 'repeat' ? 'Repeat reminder' : mode === 'due' ? 'Set a due date' : 'Snooze reminder'}</h2><button className="icon-button" aria-label="Close reminder settings" disabled={saving} onClick={onClose}><X size={17} /></button></div>
    <p className="timing-subject">{item.sources[0].value}</p>
    {mode === 'repeat' && item.repeat_origin === 'writing' && <p className="timing-hint">Set from your writing. Change the schedule below, or choose Doesn’t repeat to stop it.</p>}
    {mode === 'snooze' && <div className="snooze-presets">{[[1, 'Tomorrow'], [3, 'In 3 days'], [7, 'Next week']].map(([days, label]) => <button key={days} className="small-button" disabled={saving} onClick={() => save({snoozed_until: afterDays(today, days as number)})}>{label}</button>)}</div>}
    <form onSubmit={event => { event.preventDefault(); const chosen = String(new FormData(event.currentTarget).get('reminder-date') || ''); void save(mode === 'repeat' ? {frequency: repeat || null, start_date: chosen || null} : mode === 'due' ? {due_date: chosen || null} : {snoozed_until: chosen}) }}>
      {mode === 'repeat' && <label className="timing-date">Repeat<select name="frequency" value={repeat} disabled={saving} onChange={event => setRepeat(event.target.value as Repeat | '')}><option value="">Doesn't repeat</option><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>}
      <label className="timing-date">{mode === 'repeat' ? 'Next due date' : mode === 'due' ? 'Due date' : 'Show again on'}<input name="reminder-date" type="date" value={value} min={mode === 'snooze' ? afterDays(today, 1) : undefined} max={mode === 'repeat' || item.repeat ? '9998-12-31' : undefined} required={mode === 'snooze' || mode === 'repeat' && !!repeat || mode === 'due' && !!item.repeat} disabled={saving} onInput={event => setValue(event.currentTarget.value)} onChange={event => setValue(event.target.value)} /></label>
      <p className="timing-hint">{mode === 'repeat' ? repeat ? 'Marking done or skipping schedules the next future date. Missed periods won’t pile up.' + (repeat === 'monthly' ? ' Shorter months use their last day, then return to your chosen day.' : '') : 'Turning repeat off keeps the next occurrence as a one-time reminder.' : mode === 'due' ? item.repeat ? 'Changing this date also sets the day for future repeats.' : 'Leave the date empty to keep this in Anytime.' : 'It will return on this day. Its due date stays the same.'}</p>
      {mode === 'due' && item.original_due_start && <p className="timing-hint">From your writing: {dateLabel({...item, due_start: item.original_due_start, due_end: item.original_due_end}, today)}</p>}
      {error && <p className="timing-error" role="alert">{error}</p>}
      <div className="timing-footer">{mode === 'due' && !item.repeat && item.due_date_overridden && <button className="text-button" type="button" disabled={saving} onClick={() => save({reset_due_date: true})}>Use date from writing</button>}<button className="primary" disabled={saving || mode === 'snooze' && !value}>{saving ? 'Saving…' : mode === 'repeat' ? 'Save repeat' : mode === 'due' ? 'Save date' : 'Snooze'}</button></div>
    </form>
  </dialog>, document.body)
}

function ActionDropdown({label, disabled, children}: {label: string; disabled: boolean; children: React.ReactNode}) {
  const details = useRef<HTMLDetailsElement>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return
    const close = (event: PointerEvent) => {
      if (!details.current?.contains(event.target as Node)) details.current?.removeAttribute('open')
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        details.current?.removeAttribute('open')
        details.current?.querySelector('summary')?.focus()
      }
    }
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', close); document.removeEventListener('keydown', escape) }
  }, [open])
  return <details className="action-dropdown" ref={details} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary aria-label={`More options: ${label}`} aria-disabled={disabled} onClick={event => { if (disabled) event.preventDefault() }}>More <ChevronDown size={13} /></summary>
    <div className="action-dropdown-panel" onClick={event => { if ((event.target as Element).closest('button')) details.current?.removeAttribute('open') }}>
      {children}
    </div>
  </details>
}
