import { useEffect, useRef, useState } from 'react'
import { ArrowRight, ArrowUpRight, BookOpen, Check, ChevronLeft, Download, FileText, Flower2, Layers3, LoaderCircle, Plus, Search, ShieldCheck, Sparkles, Trash2, Users, X } from 'lucide-react'

type Category = 'birthday' | 'interest' | 'plan' | 'commitment' | 'relationship' | 'context'
type Candidate = { person: string; category: Category; value: string; evidence: string }
type Note = { id: number; text: string; status: string; candidates: Candidate[] | null; error: string | null; created_at: string }
type Memory = Candidate & { id: number; note_id: number; active: number; edited: number; replaces_id: number | null }
type Person = { id: number; name: string; memories: Memory[] }
type State = { notes: Note[]; people: Person[]; inference_configured: boolean; model: string }
type Draft = Candidate & { candidate_index: number; selected: boolean; replaces_id: number | null }
const categories: Category[] = ['birthday', 'interest', 'plan', 'commitment', 'relationship', 'context']
const categoryLabels: Record<Category, string> = { birthday: 'Important dates', interest: 'Things they love', plan: 'Plans & intentions', commitment: 'Promises & commitments', relationship: 'Their connections', context: 'Shared context' }
const samples = [
  { title: 'Coffee with Maya', text: 'Had coffee with Maya today. Maya’s birthday is June 12, and she loves hiking and ceramics. I promised Maya I would send her the trail guide.' },
  { title: 'Catching up with Stephen', text: 'Stephen is training for his first half marathon. Stephen’s birthday is November 8. I promised Stephen I would check in about his training next week.' },
  { title: 'A correction about Drake', text: 'Drake told me his birthday is April 18, not April 8 as I had written before. Drake enjoys jazz and is learning to play piano.' },
]
const normalize = (name: string) => name.trim().replace(/\s+/g, ' ').toLocaleLowerCase()
const date = (value: string) => new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

class ApiError extends Error {
  constructor(message: string, public noteId?: number) { super(message) }
}

async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined })
  if (!response.ok) {
    const result = await response.json().catch(() => null)
    const detail = result?.detail
    throw new ApiError(typeof detail === 'string' ? detail : detail?.message || 'Something went wrong. Please try again.', detail?.note_id)
  }
  return response.status === 204 ? undefined as T : response.json()
}

export default function App() {
  const [data, setData] = useState<State | null>(null)
  const [view, setView] = useState<'notes' | 'people'>('notes')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [reviewNote, setReviewNote] = useState<Note | null>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [personId, setPersonId] = useState<number | null>(null)
  const [source, setSource] = useState<Note | null>(null)
  const [search, setSearch] = useState('')
  const [deleting, setDeleting] = useState<number | null>(null)
  const modalRef = useRef<HTMLElement>(null)

  const refresh = async () => { const state = await api<State>('/state'); setData(state); return state }
  useEffect(() => { refresh().catch(err => setError(err.message)) }, [])
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
    setBusy(true); setError(''); setNotice('')
    try {
      await api<Note>(note ? `/notes/${note.id}/organize` : '/notes', 'POST', note ? undefined : { text })
      if (!note) setText('')
      setReviewNote(null)
      setNotice('Note saved. Weaver is connecting the details in the background.')
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
  const people = (data?.people || []).filter(p => p.name.toLowerCase().includes(search.toLowerCase()))
  const selectedPerson = data?.people.find(p => p.id === personId)
  const pending = data?.notes.filter(n => n.status === 'queued' || n.status === 'processing') || []
  const count = data?.people.reduce((sum, p) => sum + p.memories.filter(m => m.active).length, 0) || 0
  const chosen = drafts.filter(d => d.selected)
  const sharedPeople = selectedPerson ? (data?.people || []).filter(p => p.id !== selectedPerson.id && p.memories.some(m => selectedPerson.memories.some(own => own.note_id === m.note_id))) : []

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Weaver home"><Flower2 size={31} strokeWidth={1.6} /><span>weaver<span className="brand-dot">.</span></span></a>
      <p className="sidebar-label">YOUR LITTLE WORLD</p>
      <nav aria-label="Main navigation">
        <button className={view === 'notes' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('notes'); setNotice('') }}><BookOpen size={18} /> Notes <span>{data?.notes.length || 0}</span></button>
        <button className={view === 'people' ? 'nav-item active' : 'nav-item'} onClick={() => { setView('people'); setNotice('') }}><Users size={18} /> People <span>{data?.people.length || 0}</span></button>
      </nav>
      <div className="sidebar-bottom"><div className="private-icon"><ShieldCheck size={19} /></div><strong>Your memory, your control.</strong><p>Saved on this device.<br />Notes and relevant memories are sent to Nebius to connect the details.</p><a href="/api/export" download><Download size={14} /> Export your memories</a></div>
      <div className="workspace"><span className="workspace-avatar">W</span><div>Personal workspace<small>Local · First edition</small></div></div>
    </aside>

    <div className="main-shell">
      <header className="topbar"><div>Personal workspace <span>/</span> <strong>{view === 'notes' ? 'Notes' : 'People'}</strong></div><span className="connection"><i className={data?.inference_configured ? '' : 'offline'} />{data?.inference_configured ? 'Nebius connected' : 'Checking connection'}</span></header>
      <main>
        <div className="page-heading"><div><p className="eyebrow">A LITTLE ATTENTION GOES A LONG WAY</p><h1>{view === 'notes' ? 'Remember what matters.' : 'The people in your world.'}</h1><p className="subtitle">{view === 'notes' ? 'Small details. Meaningful connections. A place to keep both.' : 'The things that make them, them. Kept together, with care.'}</p></div><span className="edition">YOUR PERSONAL MEMORY</span></div>

        {error && <div className="alert error" role="alert"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={17} /></button></div>}
        {notice && <div className="alert success" role="status"><Check size={18} /><span>{notice}</span><button aria-label="Dismiss notification" onClick={() => setNotice('')}><X size={17} /></button></div>}
        {!data && <div className="loading-state"><LoaderCircle className="spin" />{error ? <button onClick={() => refresh().then(() => setError('')).catch(e => setError(e.message))}>Retry loading Weaver</button> : 'Opening your workspace…'}</div>}

        {data && view === 'notes' && <div className="notes-layout"><section className="notes-main">
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
          </section> : <section className="card composer">
            <div className="card-heading"><span className="section-icon"><Plus size={21} /></span><div><h2>Drop a thought. Leave the rest to Weaver.</h2><p>People, plans, promises. Automatically connected and remembered.</p></div></div>
            <label className="sr-only" htmlFor="note-text">Your note</label><textarea id="note-text" maxLength={12000} value={text} disabled={busy} onChange={e => setText(e.target.value)} placeholder="Had coffee with Maya. Her birthday is June 12, she’s been getting into ceramics, and I promised to send her that trail guide…" />
            <div className="composer-footer"><span><ShieldCheck size={14} /> Organized automatically. Always yours to change.</span><button className="primary" disabled={busy || !text.trim()} onClick={() => extract()}>{busy ? <><LoaderCircle size={16} className="spin" /> Saving your note…</> : <>Save note <ArrowRight size={16} /></>}</button></div>
            <p className="inference-note">Weaver uses Nemotron on Nebius to organize your note with relevant existing memories. Saved notes and profiles stay on this device.</p>
          </section>}

          {!reviewNote && !data.notes.length && <section className="examples"><div className="section-title"><h3>A place to start</h3><span>FICTIONAL SAMPLE NOTES</span></div><div className="sample-grid">{samples.map((sample, i) => <button key={sample.title} disabled={busy} onClick={() => setText(sample.text)}><span className={`sample-number sample-${i}`}>0{i + 1}</span><strong>{sample.title}</strong><p>{sample.text}</p><span className="sample-action">Try this note <ArrowUpRight size={14} /></span></button>)}</div></section>}

          {!!data.notes.length && <section className="note-history"><div className="section-title"><h3>Your notes <span className="count">{data.notes.length}</span></h3><span>{pending.length ? `${pending.length} ORGANIZING` : 'A THREAD OF EVERYDAY MOMENTS'}</span></div>{data.notes.map(note => <article className="note-row" key={note.id}><div className="note-row-icon"><FileText size={18} /></div><div className="note-row-content"><button className="note-preview" onClick={() => setSource(note)}>{note.text}</button><span className="note-meta">{date(note.created_at)} <span>·</span> <span className={note.status === 'pending' ? 'pending-text' : ''}>{note.status === 'queued' ? 'Queued · saved on this device' : note.status === 'processing' ? 'Connecting the details…' : note.status === 'failed' ? 'Saved · organization paused' : note.status === 'pending' ? 'Ready to organize' : note.status === 'organized' ? 'Organized automatically' : 'Remembered'}</span></span>{(note.status === 'organized' || note.status === 'reviewed') && <div className="note-connections">{data.people.filter(p => p.memories.some(m => m.note_id === note.id)).map(person => <button key={person.id} onClick={() => { setView('people'); setPersonId(person.id) }}><Users size={11} /> {person.name} <ArrowUpRight size={11} /></button>)}{note.candidates?.length === 0 && <span>No personal details found. Your note is kept.</span>}</div>}{note.error && <p className="note-error">{note.error}</p>}</div><div className="note-row-actions">{['pending', 'failed'].includes(note.status) && <button className="small-button" disabled={busy} onClick={() => extract(note)}>{note.status === 'failed' ? 'Retry' : 'Organize'}</button>}{note.status === 'pending' && note.candidates !== null && <button className="small-button" disabled={busy} onClick={() => openReview(note)}>Inspect</button>}<button className="icon-button" aria-label={`Delete note ${note.id}`} disabled={busy} onClick={() => setDeleting(note.id)}><Trash2 size={15} /></button></div></article>)}</section>}
        </section><aside className="right-rail"><div className="quiet-card"><div className="orbit"><Flower2 size={46} strokeWidth={1} /><span className="orbit-dot" /></div><p className="eyebrow">MORE THAN A GOOD MEMORY</p><h2>Care is in<br />the little things.</h2><p>A birthday remembered.<br />A promise kept.<br />A conversation picked up<br />right where it left off.</p><div className="quiet-divider" /><span>Make room for the people.<br />We’ll help with the details.</span></div><div className="stats"><div><Users size={17} /><strong>{data.people.length}</strong><span>people remembered</span></div><div><Layers3 size={17} /><strong>{count}</strong><span>details kept</span></div></div><div className="how-it-works"><p className="eyebrow">ONE THOUGHT AT A TIME</p><p><span>01</span> Capture a moment</p><p><span>02</span> Let the details connect</p><p><span>03</span> Come back when you need it</p></div></aside></div>}

        {data && view === 'people' && <section className="people-section"><div className="people-toolbar"><label className="search"><Search size={17} /><input aria-label="Search people" placeholder="Find someone…" value={search} onChange={e => setSearch(e.target.value)} /></label><button className="primary" onClick={() => { setView('notes'); setReviewNote(null) }}><Plus size={16} /> Add a note</button></div>
          {!data.people.length ? <div className="card empty-people"><Users size={35} strokeWidth={1.2} /><h2>Every connection starts somewhere.</h2><p>Drop in a note. Weaver will build the profiles for you.</p><button className="text-button" onClick={() => setView('notes')}>Write your first note <ArrowRight size={16} /></button></div> : <div className="people-layout"><div className="people-list">{people.map(person => <button key={person.id} className={`person-card ${personId === person.id ? 'selected' : ''}`} onClick={() => setPersonId(person.id)}><span className="avatar">{person.name.slice(0, 1).toUpperCase()}</span><span><strong>{person.name}</strong><small>{person.memories.filter(m => m.active).length} memories</small></span><ArrowUpRight size={16} /></button>)}{!people.length && <p className="muted">No one matches that name.</p>}</div><div className="card profile">{selectedPerson ? <><div className="profile-heading"><span className="avatar large">{selectedPerson.name.slice(0, 1).toUpperCase()}</span><div><p className="eyebrow">A PERSON, NOT JUST A PROFILE</p><h2>{selectedPerson.name}</h2></div></div>{categories.map(category => {
            const memories = selectedPerson.memories.filter(m => m.category === category && m.active)
            return memories.length > 0 && <section className="memory-group" key={category}><h3>{categoryLabels[category]}</h3>{memories.map(memory => <MemoryView key={memory.id} memory={memory} person={selectedPerson.name} onEdited={async () => { await refresh() }} onSource={() => setSource(data.notes.find(n => n.id === memory.note_id) || null)} />)}</section>
          })}{sharedPeople.length > 0 && <section className="memory-group"><h3>Shared notes with</h3><div className="note-connections">{sharedPeople.map(p => <button key={p.id} onClick={() => setPersonId(p.id)}><Users size={11} /> {p.name} <ArrowUpRight size={11} /></button>)}</div></section>}<details className="past-memories"><summary>Previous memories ({selectedPerson.memories.filter(m => !m.active).length})</summary>{selectedPerson.memories.filter(m => !m.active).map(m => <MemoryView key={m.id} memory={m} person={selectedPerson.name} onEdited={async () => { await refresh() }} onSource={() => setSource(data.notes.find(n => n.id === m.note_id) || null)} />)}</details></> : <div className="profile-placeholder"><Flower2 size={38} strokeWidth={1} /><h2>Get to know your memories.</h2><p>Choose someone to see the details you’ve kept.</p></div>}</div></div>}
        </section>}
        <footer className="page-footer"><Flower2 size={15} /> Woven from the moments that matter.<span>Powered by NVIDIA Nemotron · Nebius Token Factory</span></footer>
      </main>
    </div>
    {source && <div className="modal-backdrop" onClick={() => setSource(null)}><section ref={modalRef} className="modal" role="dialog" aria-modal="true" aria-labelledby="source-title" onClick={e => e.stopPropagation()}><div className="modal-heading"><h2 id="source-title">The original moment</h2><button className="icon-button" autoFocus aria-label="Close source note" onClick={() => setSource(null)}><X size={20} /></button></div><p className="eyebrow">NOTE {source.id} · {date(source.created_at)}</p><p className="source-text">{source.text}</p><p className="muted">Your original note is kept alongside the details Weaver remembered.</p></section></div>}
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
