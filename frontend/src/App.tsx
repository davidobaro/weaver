import { workspaceStorage, draftLocation, isDemo } from './demoSession'
import { useEffect, useRef, useState } from 'react'
import ForYou from './ForYou'
import PageHeading from './PageHeading'
import DemoNotice from './DemoNotice'
import Notifications from './Notifications'
import WorkspaceSearch from './WorkspaceSearch'
import QuickNote from './QuickNote'
import { journalDraftKey, readWritingDrafts } from './writingDrafts'
import EntryReader from './EntryReader'
import EntryNoticed from './EntryNoticed'
import EntryLimit, { ENTRY_CHARACTER_LIMIT, entryLength } from './EntryLimit'
import Wordmark from './Wordmark'
import WovenThreads from './WovenThreads'
import { entryDate as formatEntryDate } from './entries'
import type { Entry as Note, EntryKind } from './entries'
import IdentityTools, { IdentityQuestion } from './IdentityTools'
import type { Alias, Match, Merge } from './IdentityTools'
import { api, ApiError, exportWorkspace } from './api'
import { ArrowRight, ArrowUpRight, BookOpen, Check, ChevronLeft, Download, FileText, Flower2, Lightbulb, LoaderCircle, Plus, Search, ShieldCheck, Sparkles, Trash2, Users, X } from 'lucide-react'

type Category = 'birthday' | 'interest' | 'plan' | 'commitment' | 'relationship' | 'context'
type Candidate = { person: string; category: Category; value: string; evidence: string }
type Memory = Candidate & { id: number; note_id: number; note_revision?: number; active: number; edited: number; replaces_id: number | null }
type AboutFact = { memory_id: number; note_id: number; note_revision?: number; label: string; value: string; evidence: string; noted_at: string; edited: boolean }
type Person = { id: number; name: string; aliases?: Alias[]; memories: Memory[]; about?: { facts: AboutFact[]; note_count: number } }
type State = { identity_matches?: Match[]; people_merges?: Merge[]; notes: Note[]; people: Person[]; inference_configured: boolean; model: string }
type Draft = Candidate & { candidate_index: number; selected: boolean; replaces_id: number | null }
const categories: Category[] = ['birthday', 'interest', 'plan', 'commitment', 'relationship', 'context']
const categoryLabels: Record<Category, string> = { birthday: 'Important dates', interest: 'Things they love', plan: 'Plans & intentions', commitment: 'Promises & commitments', relationship: 'Their connections', context: 'Shared context' }

const samples = [
  { title: 'Coffee with Maya', text: 'Had coffee with Maya today. Maya’s birthday is June 12, and she loves hiking and ceramics. I promised Maya I would send her the trail guide.' },
  { title: 'Catching up with Stephen', text: 'Stephen is training for his first half marathon. Stephen’s birthday is November 8. I promised Stephen I would check in about his training next week.' },
  { title: 'A correction about Drake', text: 'Drake told me his birthday is April 18, not April 8 as I had written before. Drake enjoys jazz and is learning to play piano.' },
]
const normalize = (name: string) => name.trim().replace(/\s+/g, ' ').toLocaleLowerCase()

const localToday = () => { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}` }

export default function App() {
  const [data, setData] = useState<State | null>(null)
  const [view, setView] = useState<'notes' | 'people' | 'for-you'>(() => window.location.hash === '#for-you' ? 'for-you' : window.location.hash === '#people' ? 'people' : 'notes')
  const [initialDrafts] = useState(() => readWritingDrafts(localToday(), workspaceStorage))
  const initialDraft = initialDrafts.journal
  const [quickDraft, setQuickDraft] = useState(initialDrafts.quick)
  const [text, setText] = useState(initialDraft.text)
  const [title, setTitle] = useState(initialDraft.title)
  const [entryDate, setEntryDate] = useState(initialDraft.entryDate)
  const [entryFilter, setEntryFilter] = useState<'all' | EntryKind>('all')
  const [entrySearch, setEntrySearch] = useState('')
  const [draftStored, setDraftStored] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [reviewNote, setReviewNote] = useState<Note | null>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [personId, setPersonId] = useState<number | null>(0)
  const [source, setSource] = useState<Note | null>(null)
  const [search, setSearch] = useState('')
  const [deleting, setDeleting] = useState<number | null>(null)
  const modalRef = useRef<HTMLElement>(null)

  useEffect(() => {
    try {
      if (text || title) { workspaceStorage.setItem(journalDraftKey, JSON.stringify({text, title, entryDate})); setDraftStored(true) }
      else { workspaceStorage.removeItem(journalDraftKey); setDraftStored(false) }
    } catch { setDraftStored(false) }
  }, [text, title, entryDate])

  useEffect(() => { window.history.replaceState(null, '', `#${view}`) }, [view])
  const refresh = async () => { const state = await api<State>('/state'); setData(state); return state }
  useEffect(() => { refresh().catch(err => setError(err.message)) }, [])
  const openSource = async (id: number, revision?: number) => {
    const current = data?.notes.find(note => note.id === id)
    if (current && (!revision || revision === (current.revision || 1))) { setSource(current); return }
    try { setSource(await api<Note>(`/notes/${id}${revision ? `?revision=${revision}` : ''}`)) }
    catch (err) { setError((err as Error).message) }
  }
  const organizing = data?.notes.some(n => n.status === 'queued' || n.status === 'processing') || false
  useEffect(() => {
    if (!organizing) return
    const timer = window.setInterval(() => { refresh().catch(() => {}) }, 1500)
    return () => window.clearInterval(timer)
  }, [organizing])
  useEffect(() => {
    if (!source && deleting === null) return
    const previousFocus = document.activeElement as HTMLElement | null
    const focusable = () => Array.from(modalRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]') || [])
    focusable()[0]?.focus()
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setSource(null); setDeleting(null) }
      if (event.key === 'Tab') {
        const items = focusable()
        const target = event.shiftKey ? items.at(-1) : items[0]
        if (document.activeElement === (event.shiftKey ? items[0] : items.at(-1))) { event.preventDefault(); target?.focus() }
      }
    }
    window.addEventListener('keydown', handler)
    return () => { window.removeEventListener('keydown', handler); previousFocus?.focus() }
  }, [source, deleting])

  const openReview = (note: Note) => {
    setReviewNote(note)
    setDrafts((note.candidates || []).map((c, i) => ({ ...c, candidate_index: i, selected: true, replaces_id: null })))
    setView('notes'); setError(''); setNotice('')
  }
  const extract = async (note?: Note) => {
    if (!note && entryLength(text) > ENTRY_CHARACTER_LIMIT) return
    setBusy(true); setError(''); setNotice('')
    try {
      await api<Note>(note ? `/notes/${note.id}/organize` : '/notes', 'POST', note ? undefined : { text, kind: 'journal', title, entry_date: entryDate })
      if (!note) { setText(''); setTitle('') }
      setReviewNote(null)
      setNotice(note ? 'Entry saved. Weaver will take it from here.' : 'Journal entry saved.')
    } catch (err) {
      setError((err as Error).message)
      if (!note && err instanceof ApiError && err.noteId) setText('')
    }
    finally { await refresh().catch(() => {}); setBusy(false) }
  }
  const save = async () => {
    if (!reviewNote) return
    setBusy(true); setError('')
    try {
      const chosen = drafts.filter(d => d.selected)
      await api(`/notes/${reviewNote.id}/review`, 'POST', { memories: chosen.map(({ candidate_index, person, category, value, replaces_id }) => ({ candidate_index, person, category, value, replaces_id })) })
      const next = await refresh()
      setReviewNote(null)
      setNotice(chosen.length ? `${chosen.length} ${chosen.length === 1 ? 'memory' : 'memories'} saved. A little more remembered.` : 'Review complete. No memories were added.')
      if (chosen.length) { setView('people'); setPersonId(next.people.find(p => normalize(p.name) === normalize(chosen[0].person))?.id ?? null) }
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  const remove = async (id: number) => {
    setBusy(true); setError('')
    try {
      await api(`/notes/${id}`, 'DELETE'); await refresh(); setDeleting(null); setSource(null)
      if (reviewNote?.id === id) setReviewNote(null)
      setNotice('Note and its memories deleted.')
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  const update = (index: number, patch: Partial<Draft>) => setDrafts(items => items.map((item, i) => i === index ? { ...item, ...patch } : item))
  const people = (data?.people || []).filter(p => [p.name, ...(p.aliases || []).map(a => a.name)].some(name => normalize(name).includes(normalize(search))))
  const selectedPerson = data?.people.find(p => p.id === personId)
  const entries = (data?.notes || []).filter(entry => (entryFilter === 'all' || (entry.kind || 'note') === entryFilter) && `${entry.title || ''} ${entry.text}`.toLocaleLowerCase().includes(entrySearch.toLocaleLowerCase()))
  const identityChanged = async (id?: number) => { await refresh(); if (id) setPersonId(id) }
  const pending = data?.notes.filter(n => n.status === 'queued' || n.status === 'processing') || []
  const chosen = drafts.filter(d => d.selected)
  const sharedPeople = selectedPerson ? (data?.people || []).filter(p => p.id !== selectedPerson.id && p.memories.some(m => selectedPerson.memories.some(own => own.note_id === m.note_id))) : []

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Weaver home"><WovenThreads /><Wordmark /></a>
      <div className="sidebar-nav-spacer" />
      <nav aria-label="Main navigation">
        <button className={view === 'notes' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('notes'); setNotice('') }}><BookOpen size={18} /> Journal <span>{data?.notes.length || 0}</span></button>
        <button className={view === 'for-you' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('for-you'); setNotice('') }}><Lightbulb size={18} /> Insights</button>
        <button className={view === 'people' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('people'); setNotice('') }}><Users size={18} /> People <span>{data?.people.length || 0}</span></button>
      </nav>
      <div className="sidebar-bottom"><details className="data-details"><summary><ShieldCheck size={14} /> About your data</summary><p>{isDemo() ? 'Temporary server workspace. Entries are cleared after inactivity or a server restart.' : 'Saved on this device.'} Entries and relevant memories are sent to Nebius to connect the details.</p></details><button className="export-workspace" onClick={()=>void exportWorkspace().catch(err=>setError(err.message))}><Download size={14} /> Export your memories</button></div>
      <div className="workspace"><span className="workspace-avatar">W</span><div>Personal workspace<small>{isDemo() ? 'Temporary demo' : 'Local · First edition'}</small></div></div>
    </aside>

    <div className="main-shell">
      <header className="topbar"><div>Personal workspace<span>/</span><strong>{view === 'notes' ? 'Journal' : view === 'for-you' ? 'Insights' : 'People'}</strong></div><div className="topbar-actions"><WorkspaceSearch revision={data} onSource={openSource} onPerson={id => { setPersonId(id); setView('people') }} /><Notifications revision={data} onOpen={() => setView('for-you')} /><span className="connection"><i className={data?.inference_configured ? '' : 'offline'} />{data?.inference_configured ? 'Nebius connected' : 'Checking connection'}</span></div></header>
      <DemoNotice/><main className={`workspace-page ${view === 'notes' ? 'notes-page' : view === 'for-you' ? 'for-you-page' : 'people-page'}`}>
        {view === 'for-you' ? <PageHeading title="Insights" subtitle="A few things worth a little attention." /> : view === 'people' ? <PageHeading title="The people in your world." subtitle="The things that make them, them. Kept together, with care." /> : null}

        {error && <div className="alert error" role="alert"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={17} /></button></div>}
        {notice && <div className="alert success" role="status"><Check size={18} /><span>{notice}</span><button aria-label="Dismiss notification" onClick={() => setNotice('')}><X size={17} /></button></div>}
        {!data && <div className="loading-state"><LoaderCircle className="spin" />{error ? <button onClick={() => refresh().then(() => setError('')).catch(e => setError(e.message))}>Retry loading Weaver</button> : 'Opening your workspace…'}</div>}

        {data && view === 'for-you' && <ForYou revision={data} onSource={openSource} onPerson={id => { setPersonId(id); setView('people') }} onAddNote={() => { setView('notes'); setReviewNote(null) }} />}

        {data && view === 'notes' && <div className="notes-layout"><section className="notes-main">
          <PageHeading title="A place for your days." subtitle="A quick thought or a longer story. Make room for both." />
          {reviewNote ? <section className="card review-card">
            <div className="card-heading"><span className="section-icon"><Sparkles size={19} /></span><div><h2>A few things worth remembering</h2><p>Check each detail. Edit it, skip it, or make it part of your memory.</p></div></div>
            <button className="source-link review-source" onClick={() => setSource(reviewNote)}><FileText size={14} /> Read original note <ArrowUpRight size={13} /></button>
            {!drafts.length && <div className="empty-inline">No clear memories about named people were found. You can finish this review or return to your notes.</div>}
            <div className="candidate-list">{drafts.map((draft, index) => {
              const existing = data.people.find(p => normalize(p.name) === normalize(draft.person))?.memories.filter(m => m.active) || []
              return <article key={index} className={`candidate ${draft.selected ? '' : 'skipped'}`}>
                <label className="candidate-check"><input type="checkbox" checked={draft.selected} disabled={busy} onChange={e => update(index, { selected: e.target.checked })} /><span>{draft.selected ? 'Keep this memory' : 'Skip this memory'}</span><span className={`tag ${draft.category}`}>{draft.category}</span></label>
                <div className="candidate-fields"><label>Person<input list="people-names" maxLength={120} value={draft.person} disabled={!draft.selected || busy} onChange={e => update(index, { person: e.target.value, replaces_id: null })} /></label><label>Kind<select value={draft.category} disabled={!draft.selected || busy} onChange={e => update(index, { category: e.target.value as Category })}>{categories.map(c => <option key={c}>{c}</option>)}</select></label></div>
                <label className="memory-field">Memory<textarea maxLength={1000} value={draft.value} disabled={!draft.selected || busy} onChange={e => update(index, { value: e.target.value })} /></label>
                <blockquote>“{draft.evidence}”<small>FROM YOUR NOTE</small></blockquote>
                {!!existing.length && <label className="replacement">How should this be saved?<select value={draft.replaces_id || ''} disabled={!draft.selected || busy} onChange={e => update(index, { replaces_id: e.target.value ? Number(e.target.value) : null })}><option value="">Add as a new memory</option>{existing.map(m => <option key={m.id} value={m.id}>Replace: {m.value}</option>)}</select></label>}
              </article>
            })}</div>
            <datalist id="people-names">{data.people.map(p => <option key={p.id} value={p.name} />)}</datalist>
            <div className="review-actions"><button className="text-button" disabled={busy} onClick={() => setReviewNote(null)}><ChevronLeft size={15} /> Review later</button><button className="primary" disabled={busy || chosen.some(d => !d.person.trim() || !d.value.trim())} onClick={save}>{busy ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{chosen.length ? `Save ${chosen.length} ${chosen.length === 1 ? 'memory' : 'memories'}` : 'Finish without saving'}</button></div>
          </section> : <section className="card composer writing-composer journal-composer" aria-label="Writing space">
            <div className="writing-toolbar"><span className="journal-writing-label"><BookOpen size={14} /> Journal entry</span><div className="journal-toolbar-actions"><label className="entry-date-label"><span className="sr-only">Entry date</span><input aria-label="Entry date" type="date" value={entryDate} disabled={busy} onChange={event => setEntryDate(event.target.value)} /></label><QuickNote draft={quickDraft} onChange={setQuickDraft} onSaved={() => { setNotice('Note saved. Weaver will take it from here.'); void refresh().catch(err => setError(err.message)) }} /></div></div>
            <label className="sr-only" htmlFor="entry-title">Entry title</label><input className="entry-title" id="entry-title" maxLength={180} value={title} disabled={busy} onChange={event => setTitle(event.target.value)} placeholder="Give today a title, if you like…" />
            <label className="sr-only" htmlFor="note-text">Your journal entry</label><textarea id="note-text" aria-describedby="new-entry-limit" aria-invalid={entryLength(text) > ENTRY_CHARACTER_LIMIT} value={text} disabled={busy} onChange={event => setText(event.target.value)} placeholder={'What’s on your mind?\n\nStart anywhere. The small moments count, too.'} />
            <EntryLimit text={text} id="new-entry-limit" />
            <div className="composer-footer"><span className="draft-indicator" role="status">{text || title ? draftStored ? draftLocation() : 'Draft not backed up — keep this page open' : ''}</span><button className="primary" disabled={busy || !text.trim() || entryLength(text) > ENTRY_CHARACTER_LIMIT || !entryDate} onClick={() => extract()}>{busy ? <><LoaderCircle size={16} className="spin" /> Saving…</> : <>Save entry <ArrowRight size={16} /></>}</button></div>
          </section>}



          {!reviewNote && !data.notes.length && <p className="notes-empty">Your entries will appear here. Write for yourself; Weaver will connect the details when there are any.<button className="text-button" disabled={busy} onClick={() => setText(samples[0].text)}>Try an example</button></p>}

        </section><aside className="journal-suggestions" aria-label="Insights alongside your journal"><div className="journal-suggestions-heading"><h2>Insights</h2><button className="source-link" onClick={() => setView('for-you')}>Open page <ArrowUpRight size={13} /></button></div><ForYou compact onOpenAll={() => setView('for-you')} revision={data} onSource={openSource} onPerson={id => { setPersonId(id); setView('people') }} onAddNote={() => document.getElementById('note-text')?.focus()} /></aside>

          {!!data.notes.length && <section className="note-history"><div className="section-title"><h3>Your entries</h3>{pending.length > 0 && <span className="organizing-status" role="status"><LoaderCircle size={12} className="spin" aria-hidden="true" />{pending.length === 1 ? 'Organizing 1 note…' : `Organizing ${pending.length} notes…`}</span>}</div><div className="entry-list-toolbar"><div className="entry-filters" role="group" aria-label="Filter entries">{(['all', 'note', 'journal'] as const).map(filter => <button key={filter} aria-pressed={entryFilter === filter} onClick={() => setEntryFilter(filter)}>{filter === 'all' ? 'All' : filter === 'note' ? 'Notes' : 'Journal'}</button>)}</div><label className="entry-search"><Search size={14} /><input aria-label="Search entries" placeholder="Find an entry…" value={entrySearch} onChange={event => setEntrySearch(event.target.value)} /></label></div>{!entries.length && <p className="muted">No entries match this view.</p>}{entries.map(note => <article className="note-row" key={note.id}><div className="note-row-content"><button className={`note-preview ${note.kind === 'journal' ? 'journal-preview' : ''}`} onClick={() => setSource(note)}>{(note.title || note.kind === 'journal') && <strong>{note.title || 'Journal entry'}</strong>}<span>{note.text}</span></button><span className="note-meta">{formatEntryDate(note.entry_date || note.created_at)}{(note.revision || 1) > 1 && <><span>·</span><span>Edited</span></>}{note.kind === 'journal' && <><span>·</span><span>Journal</span></>}{['queued', 'processing', 'failed', 'pending'].includes(note.status) && <><span>·</span><span className="pending-text organizing-status" role={note.status === 'queued' || note.status === 'processing' ? 'status' : undefined}>{(note.status === 'queued' || note.status === 'processing') && <LoaderCircle size={11} className="spin" aria-hidden="true" />}{note.status === 'queued' ? 'Queued' : note.status === 'processing' ? 'Organizing…' : note.status === 'failed' ? 'Organization paused' : 'Ready to organize'}</span></>}</span><EntryNoticed key={`${note.id}-${note.revision || 1}`} entry={note} onPerson={id => { setView('people'); setPersonId(id) }} onSource={() => setSource(note)} />{note.error && <p className="note-error">{note.error}</p>}</div><div className="note-row-actions">{['pending', 'failed'].includes(note.status) && <button className="small-button" disabled={busy} onClick={() => extract(note)}>{note.status === 'failed' ? 'Retry' : 'Organize'}</button>}{note.status === 'pending' && note.candidates !== null && <button className="small-button" disabled={busy} onClick={() => openReview(note)}>Inspect</button>}<button className="icon-button" aria-label={`Delete note ${note.id}`} disabled={busy} onClick={() => setDeleting(note.id)}><Trash2 size={15} /></button></div></article>)}</section>}


        </div>}

        {data && view === 'people' && <section className="people-section"><div className="people-toolbar"><label className="search"><Search size={17} /><input aria-label="Search people" placeholder="Find someone…" value={search} onChange={e => setSearch(e.target.value)} /></label><button className="primary" onClick={() => { setView('notes'); setReviewNote(null) }}><Plus size={16} /> Add a note</button></div>
          {!!data.identity_matches?.length && <IdentityQuestion key={`${data.identity_matches[0].source_id}-${data.identity_matches[0].target_id}`} match={data.identity_matches[0]} onChanged={identityChanged} />}
          {<div className="people-layout"><div className="people-list"><button className={`person-card you-tab ${personId === 0 ? 'selected' : ''}`} aria-label="You — personal tasks" aria-pressed={personId === 0} onClick={() => setPersonId(0)}><span className="avatar">Y</span><span><strong>You</strong><small>Your tasks &amp; reminders</small></span><ArrowUpRight size={16} /></button>{people.map(person => <button key={person.id} className={`person-card ${personId === person.id ? 'selected' : ''}`} onClick={() => setPersonId(person.id)}><span className="avatar">{person.name.slice(0, 1).toUpperCase()}</span><span><strong>{person.name}</strong><small>{person.memories.filter(m => m.active).length} {person.memories.filter(m => m.active).length === 1 ? 'memory' : 'memories'}</small></span><ArrowUpRight size={16} /></button>)}{!people.length && <p className="muted">{search ? 'No one matches that name.' : 'Other people will appear as you write about them.'}</p>}</div><div className="card profile">{personId === 0 ? <><div className="profile-heading"><span className="avatar large">Y</span><div><p className="eyebrow">A LITTLE SPACE FOR YOU</p><h2>You</h2><p className="profile-you-description">Your tasks, plans, reminders, and goals.</p></div></div><section className="profile-obligations" aria-label="Your tasks and obligations"><h3>Tasks &amp; obligations</h3><ForYou key="you" profile fixedScope="personal" revision={data} onSource={openSource} onPerson={setPersonId} onAddNote={() => setView('notes')} /></section></> : selectedPerson ? <><div className="profile-heading"><span className="avatar large">{selectedPerson.name.slice(0, 1).toUpperCase()}</span><div><p className="eyebrow">A PERSON, NOT JUST A PROFILE</p><h2>{selectedPerson.name}</h2>{!!selectedPerson.aliases?.length && <p className="profile-aliases">Also known as {selectedPerson.aliases.map(a => a.name).join(', ')}</p>}</div></div><section className="profile-about" aria-label={`About ${selectedPerson.name}`}><div className="about-heading"><h3>About</h3><span>From your notes</span></div>{selectedPerson.about?.facts.length ? <dl className="about-facts">{selectedPerson.about.facts.map(fact => <div key={fact.memory_id}><dt>{fact.label}</dt><dd><p>{fact.value}</p><button className="source-link" onClick={() => openSource(fact.note_id, fact.note_revision)}>Noted {formatEntryDate(fact.noted_at)} <ArrowUpRight size={11} /></button></dd></div>)}</dl> : <p className="about-empty">Weaver will build a quick picture here as you add notes about {selectedPerson.name}.</p>}</section><section className="profile-obligations" aria-label={`Tasks involving ${selectedPerson.name}`}><h3>Tasks &amp; obligations</h3><ForYou key={selectedPerson.id} profile fixedScope="others" personId={selectedPerson.id} revision={data} onSource={openSource} onPerson={setPersonId} onAddNote={() => setView('notes')} /></section><details className="profile-details"><summary>All memories</summary>{categories.map(category => {
            const memories = selectedPerson.memories.filter(m => m.category === category && m.active)
            return memories.length > 0 && <section className="memory-group" key={category}><h3>{categoryLabels[category]}</h3>{memories.map(memory => <MemoryView key={memory.id} memory={memory} person={selectedPerson.name} onEdited={async () => { await refresh() }} onSource={() => openSource(memory.note_id, memory.note_revision)} />)}</section>
          })}{sharedPeople.length > 0 && <section className="memory-group"><h3>Shared notes with</h3><div className="note-connections">{sharedPeople.map(p => <button key={p.id} onClick={() => setPersonId(p.id)}><Users size={11} /> {p.name} <ArrowUpRight size={11} /></button>)}</div></section>}<details className="past-memories"><summary>Previous memories ({selectedPerson.memories.filter(m => !m.active).length})</summary>{selectedPerson.memories.filter(m => !m.active).map(m => <MemoryView key={m.id} memory={m} person={selectedPerson.name} onEdited={async () => { await refresh() }} onSource={() => openSource(m.note_id, m.note_revision)} />)}</details></details><IdentityTools key={selectedPerson.id} person={selectedPerson} people={data.people} merges={data.people_merges || []} onChanged={identityChanged} /></> : <div className="profile-placeholder"><Flower2 size={38} strokeWidth={1} /><h2>Get to know your memories.</h2><p>Choose someone to see the details you’ve kept.</p></div>}</div></div>}
        </section>}
        {view === 'people' && <footer className="page-footer"><Flower2 size={15} /> Woven from the moments that matter.<span>Powered by NVIDIA Nemotron · Nebius Token Factory</span></footer>}
      </main>
    </div>
    {source && <div className="modal-backdrop" onClick={() => setSource(null)}><section ref={modalRef} className={`modal ${source.kind === 'journal' ? 'journal-reader' : ''}`} role="dialog" aria-modal="true" aria-labelledby="source-title" onClick={e => e.stopPropagation()}><EntryReader key={source.id} entry={source} onClose={() => setSource(null)} onEntry={setSource} onSaved={async updated => { setSource(updated); await refresh().catch(err => setError(err.message)); setNotice('Entry saved. Connected details are updating.') }} /></section></div>}
    {deleting !== null && <div className="modal-backdrop"><section ref={modalRef} className="modal" role="alertdialog" aria-modal="true" aria-labelledby="delete-title"><h2 id="delete-title">Delete this moment?</h2><p>This removes the note and memories saved from it. Older memories it replaced will be restored where available.</p><div className="review-actions"><button className="text-button" autoFocus disabled={busy} onClick={() => setDeleting(null)}>Keep note</button><button className="danger-button" disabled={busy} onClick={() => remove(deleting)}>{busy ? 'Deleting…' : 'Delete note & memories'}</button></div></section></div>}
  </div>
}

function MemoryView({ memory, person, onSource, onEdited }: { memory: Memory; person: string; onSource: () => void; onEdited: () => Promise<void> }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(person)
  const [value, setValue] = useState(memory.value)
  const [category, setCategory] = useState(memory.category)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const save = async () => {
    setSaving(true); setError('')
    try {
      await api(`/memories/${memory.id}`, 'PATCH', {person: name, value, category})
      await onEdited(); setEditing(false)
    } catch (err) { setError((err as Error).message) }
    finally { setSaving(false) }
  }
  return <article className="saved-memory">{editing ? <div className="memory-editor"><label>Person<input aria-label="Edit person" maxLength={120} value={name} disabled={saving} onChange={e => setName(e.target.value)} /></label><label>Kind<select aria-label="Edit kind" value={category} disabled={saving} onChange={e => setCategory(e.target.value as Category)}>{categories.map(c => <option key={c}>{c}</option>)}</select></label><label className="edit-value">Memory<textarea aria-label="Edit memory" maxLength={1000} value={value} disabled={saving} onChange={e => setValue(e.target.value)} /></label>{error && <p role="alert">{error}</p>}<button className="small-button" disabled={saving || !name.trim() || !value.trim()} onClick={save}>{saving ? 'Saving…' : 'Save change'}</button><button className="text-button" disabled={saving} onClick={() => setEditing(false)}>Cancel</button></div> : <p>{memory.value}</p>}<div><button className="source-link" onClick={onSource}><FileText size={13} /> Source note <ArrowUpRight size={12} /></button>{!!memory.active && !editing && <button className="source-link" onClick={() => setEditing(true)}>Edit</button>}{!!memory.edited && <span className="edited-label">Edited by you</span>}{memory.replaces_id && <span className="edited-label">Updated memory</span>}</div></article>
}
