import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowUpRight, BookOpen, CheckSquare, FileText, LoaderCircle, Search, Users, X } from 'lucide-react'
import { api } from './api'

type Kind = 'entry' | 'person' | 'memory' | 'task'
type Result = {
  id: string; kind: Kind; title: string; excerpt: string; note_id?: number | null; note_revision?: number | null;
  person_id?: number | null; person?: string; entry_date?: string; category?: string;
  status?: 'open' | 'done' | 'dismissed'; snoozed?: boolean; due_start?: string | null; repeat?: string | null; past_occurrence?: boolean
}
type Response = { results: Result[]; counts: Record<Kind, number>; total: number }
const filters: {kind: Kind | 'all'; label: string}[] = [
  {kind: 'all', label: 'All'}, {kind: 'entry', label: 'Entries'}, {kind: 'person', label: 'People'},
  {kind: 'memory', label: 'Memories'}, {kind: 'task', label: 'Tasks'},
]
const icons = {entry: BookOpen, person: Users, memory: FileText, task: CheckSquare}
const labels = {entry: 'Entry', person: 'Person', memory: 'Memory', task: 'Task'}
const formatDate = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'})

export default function WorkspaceSearch({revision, onSource, onPerson}: {
  revision: unknown; onSource: (id: number, revision?: number) => void; onPerson: (id: number) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Kind | 'all'>('all')
  const [limit, setLimit] = useState(20)
  const [response, setResponse] = useState<Response | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const dialog = useRef<HTMLDialogElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const results = useRef<HTMLDivElement>(null)
  const titleId = useId()

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const element = dialog.current!
    element.showModal(); input.current?.focus()
    return () => { element.close(); previous?.focus() }
  }, [open])

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === 'k') {
        if (!open && document.querySelector('dialog[open], [role="dialog"]')) return
        event.preventDefault(); setOpen(true); input.current?.focus()
      }
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [open])

  useEffect(() => {
    if (!open) return
    const changed = () => setRefresh(value => value + 1)
    const stored = (event: StorageEvent) => { if (event.key === 'weaver-suggestions-revision') changed() }
    window.addEventListener('focus', changed)
    window.addEventListener('weaver-suggestions-changed', changed)
    window.addEventListener('storage', stored)
    return () => { window.removeEventListener('focus', changed); window.removeEventListener('weaver-suggestions-changed', changed); window.removeEventListener('storage', stored) }
  }, [open])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setResponse(null); setError('')
    if (!query.trim()) { setLoading(false); return }
    setLoading(true)
    const timer = window.setTimeout(() => {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York'
      void api<Response>(`/search?q=${encodeURIComponent(query)}&kind=${filter}&limit=${limit}&timezone=${encodeURIComponent(timezone)}`)
        .then(value => { if (!cancelled) setResponse(value) })
        .catch(err => { if (!cancelled) setError(err.message) })
        .finally(() => { if (!cancelled) setLoading(false) })
    }, 180)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [open, query, filter, limit, revision, refresh])

  const readSource = (item: Result) => { if (item.note_id) { setOpen(false); onSource(item.note_id, item.note_revision || undefined) } }
  const openPerson = (id: number) => { setOpen(false); onPerson(id) }
  return <>
    <button className="workspace-search-trigger" aria-label="Search workspace" title="Search workspace (⌘K / Ctrl+K)" onClick={() => setOpen(true)}><Search size={15} /><span>Search</span></button>
    {open && createPortal(<dialog ref={dialog} className="workspace-search-dialog" aria-labelledby={titleId} onCancel={() => setOpen(false)} onClick={event => {
      const box = event.currentTarget.getBoundingClientRect()
      if (event.target === event.currentTarget && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) setOpen(false)
    }}>
      <div className="workspace-search-heading"><h2 id={titleId}>Find a thread.</h2><button className="icon-button" aria-label="Close workspace search" onClick={() => setOpen(false)}><X size={18} /></button></div>
      <div className="workspace-search-input"><Search size={18} /><input aria-label="Search your workspace" ref={input} autoComplete="off" spellCheck={false} value={query} maxLength={200} placeholder="A person, a memory, a task…" onChange={event => { setQuery(event.target.value); setLimit(20) }} onKeyDown={event => {
        if (event.key === 'ArrowDown' || event.key === 'Enter') {
          const first = results.current?.querySelector<HTMLButtonElement>('.search-result-title')
          if (first) { event.preventDefault(); if (event.key === 'Enter') first.click(); else first.focus() }
        }
      }} />{query && <button className="icon-button" aria-label="Clear workspace search" onClick={() => { setQuery(''); setLimit(20); input.current?.focus() }}><X size={14} /></button>}</div>
      <div className="workspace-search-filters" role="group" aria-label="Filter search results">{filters.map(item => <button key={item.kind} aria-label={item.label} aria-pressed={filter === item.kind} onClick={() => { setFilter(item.kind); setLimit(20) }}>{item.label}{response && <span>{item.kind === 'all' ? Object.values(response.counts).reduce((a, b) => a + b, 0) : response.counts[item.kind]}</span>}</button>)}</div>
      <div className="workspace-search-summary" role="status" aria-live="polite">{loading ? <><LoaderCircle size={13} className="spin" /> Searching…</> : error ? 'Search couldn’t load.' : response ? `${response.total} ${response.total === 1 ? 'result' : 'results'}${response.total > response.results.length ? ` · showing ${response.results.length}` : ''}` : 'Your entries and everything woven from them.'}</div>
      <div className="workspace-search-results" ref={results} aria-label="Search results" aria-busy={loading}>
        {error && <div className="workspace-search-empty"><p role="alert">{error}</p><button className="small-button" onClick={() => setRefresh(value => value + 1)}>Try again</button></div>}
        {!query.trim() && <div className="workspace-search-empty"><Search size={25} /><p>Try a name, a hobby, or part of a reminder.</p></div>}
        {response && !response.results.length && <div className="workspace-search-empty"><p>No matches yet. Try fewer words or another name.</p></div>}
        {response?.results.map(item => {
          const Icon = icons[item.kind]
          return <article className="workspace-search-result" key={item.id}>
            <div className="search-result-meta"><span><Icon size={13} />{labels[item.kind]}</span>{item.person && <span>{item.person}</span>}{item.entry_date && <span>{formatDate(item.entry_date)}</span>}{item.status && <span>{item.snoozed ? 'Snoozed' : item.status === 'open' ? 'Open' : item.status === 'done' ? 'Done' : 'Dismissed'}{item.past_occurrence ? ' · Past occurrence' : ''}</span>}{item.due_start && <span>Due {formatDate(item.due_start)}</span>}{item.repeat && <span>{item.repeat}</span>}</div>
            <button className="search-result-title" onClick={() => item.kind === 'person' && item.person_id != null ? openPerson(item.person_id) : readSource(item)}>{item.title}<ArrowUpRight size={14} /></button>
            {item.excerpt !== item.title && <p>{item.excerpt}</p>}
            <div className="search-result-links">{item.note_id && item.kind !== 'entry' && <button className="source-link" onClick={() => readSource(item)}>Read source entry <ArrowUpRight size={11} /></button>}{item.kind !== 'person' && item.person_id != null && <button className="source-link" onClick={() => openPerson(item.person_id!)}>Open profile <ArrowUpRight size={11} /></button>}{item.kind === 'task' && item.person_id == null && <button className="source-link" onClick={() => openPerson(0)}>Your tasks <ArrowUpRight size={11} /></button>}</div>
          </article>
        })}
        {response && response.results.length < response.total && (limit < 100 ? <button className="text-button search-show-more" onClick={() => setLimit(value => Math.min(100, value + 20))}>Show more results</button> : <p className="workspace-search-limit">Try a more specific search to narrow these results.</p>)}
      </div>
    </dialog>, document.body)}
  </>
}
