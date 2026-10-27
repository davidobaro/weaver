import { useEffect, useState } from 'react'
import { Check, History, Pencil, RotateCcw, X } from 'lucide-react'
import { api } from './api'
import type { Entry, EntryKind } from './entries'
import { entryDate } from './entries'
import EntryLimit, { ENTRY_CHARACTER_LIMIT, entryLength } from './EntryLimit'

type Version = { revision: number; title: string; kind: EntryKind; entry_date: string | null; saved_at: string }
type Draft = { text: string; title: string; kind: EntryKind; entry_date: string; expected_revision: number }

export default function EntryReader({ entry, onClose, onEntry, onSaved }: {
  entry: Entry; onClose: () => void; onEntry: (entry: Entry) => void; onSaved: (entry: Entry) => Promise<void>
}) {
  const revision = entry.revision || 1
  const key = `weaver-entry-edit-v1-${entry.id}`
  const fresh = (): Draft => ({ text: entry.text, title: entry.title || '', kind: entry.kind || 'note', entry_date: entry.entry_date || '', expected_revision: revision })
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Draft>(fresh)
  const [olderDraft, setOlderDraft] = useState<Draft | null>(null)
  const [draftStored, setDraftStored] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [versions, setVersions] = useState<Version[] | null>(null)
  useEffect(() => { setEditing(false); setForm(fresh()); setError(''); setVersions(null); setOlderDraft(null) }, [entry.id, revision, entry.is_history])
  useEffect(() => {
    if (!editing || olderDraft) return
    try { localStorage.setItem(key, JSON.stringify(form)); setDraftStored(true) }
    catch { setDraftStored(false) }
  }, [editing, form, key, olderDraft])
  const begin = () => {
    let draft = fresh()
    try {
      const stored = JSON.parse(localStorage.getItem(key) || 'null')
      if (stored && typeof stored.text === 'string' && typeof stored.title === 'string' && ['note', 'journal'].includes(stored.kind)) {
        if (stored.expected_revision === revision) draft = stored
        else setOlderDraft(stored)
      }
    } catch { /* Storage is optional; the original entry remains in SQLite. */ }
    setForm(draft); setEditing(true); setError('')
  }
  const save = async () => {
    if (entryLength(form.text) > ENTRY_CHARACTER_LIMIT) return
    setBusy(true); setError('')
    try {
      const updated = await api<Entry>(`/notes/${entry.id}`, 'PATCH', { ...form, entry_date: form.entry_date || null })
      try { localStorage.removeItem(key) } catch { /* Saving still works without browser storage. */ }
      setEditing(false); setVersions(null)
      await onSaved(updated)
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  const showVersion = async (version?: number) => {
    setBusy(true); setError('')
    try { onEntry(await api<Entry>(`/notes/${entry.id}${version ? `?revision=${version}` : ''}`)) }
    catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  const history = async () => {
    if (versions) { setVersions(null); return }
    setBusy(true); setError('')
    try { const result = await api<{versions: Version[]}>(`/notes/${entry.id}/versions`); setVersions(result.versions) }
    catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  const restore = async () => {
    setBusy(true); setError('')
    try {
      const updated = await api<Entry>(`/notes/${entry.id}/restore`, 'POST', {revision, expected_revision: entry.current_revision || revision})
      await onSaved(updated)
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  return <>
    <div className="modal-heading"><h2 id="source-title">{editing ? 'Edit entry' : entry.title || (entry.kind === 'journal' ? 'Journal entry' : 'The original moment')}</h2><button className="icon-button" autoFocus aria-label="Close source note" disabled={busy} onClick={onClose}><X size={20} /></button></div>
    <div className="entry-reader-meta"><span>{entry.kind === 'journal' ? 'JOURNAL' : 'NOTE'} · {entryDate(entry.entry_date || entry.created_at)}</span><span>Version {revision}{entry.is_history ? ' · Earlier version' : ''}</span></div>
    {error && <p className="note-error" role="alert">{error}</p>}
    {entry.is_history && <p className="version-explanation">This is the writing behind an earlier version. Restoring it creates a new version and keeps manually corrected memories.</p>}
    {editing ? <div className="entry-editor">
      {olderDraft && <details className="recovered-edit"><summary>An older editing draft is saved on this device</summary><p>Review the draft before using it in place of the current entry.</p><blockquote>{olderDraft.text}</blockquote><button className="small-button" onClick={() => { setForm({...olderDraft, expected_revision: revision}); setOlderDraft(null) }}>Use recovered draft</button><button className="text-button" onClick={() => setOlderDraft(null)}>Keep current writing</button></details>}
      <label>Title <span>(optional)</span><input aria-label="Edit entry title" maxLength={180} value={form.title} disabled={busy} onChange={event => setForm({...form,title:event.target.value})} /></label>
      <div className="entry-editor-options"><label>Type<select aria-label="Edit entry type" disabled={busy} value={form.kind} onChange={event => setForm({...form,kind:event.target.value as EntryKind})}><option value="note">Quick note</option><option value="journal">Journal entry</option></select></label><label>Entry date <span>(optional)</span><input aria-label="Edit entry date" type="date" disabled={busy} value={form.entry_date} onChange={event => setForm({...form,entry_date:event.target.value})} /></label></div>
      <label>Your writing<textarea aria-label="Edit entry text" aria-describedby="edit-entry-limit" aria-invalid={entryLength(form.text) > ENTRY_CHARACTER_LIMIT} autoFocus value={form.text} disabled={busy} onChange={event => setForm({...form,text:event.target.value})} /></label>
      <EntryLimit text={form.text} id="edit-entry-limit" />
      <p className="draft-indicator">{olderDraft ? 'Choose which writing to keep before draft recovery continues' : draftStored ? 'Editing draft saved on this device' : 'Keep this page open — draft storage is unavailable'}</p>
      <div className="entry-reader-actions"><button className="primary" disabled={busy || !form.text.trim() || entryLength(form.text) > ENTRY_CHARACTER_LIMIT} onClick={save}><Check size={14} />{busy ? 'Saving…' : 'Save changes'}</button><button className="text-button" disabled={busy} onClick={() => { try { localStorage.removeItem(key) } catch { /* Optional draft storage. */ } setEditing(false) }}>Cancel edit</button></div>
      {error && <button className="text-button" disabled={busy} onClick={() => showVersion()}>View latest entry</button>}
    </div> : <><p className="source-text">{entry.text}</p><div className="entry-reader-actions">{!entry.is_history ? <button className="text-button" disabled={busy} onClick={begin}><Pencil size={13} /> Edit entry</button> : <><button className="small-button" disabled={busy} onClick={restore}><RotateCcw size={13} /> Restore this version</button><button className="text-button" disabled={busy} onClick={() => showVersion()}>View current entry</button></>}<button className="text-button" disabled={busy} onClick={history}><History size={14} /> Version history</button></div></>}
    {versions && <section className="entry-history" aria-label="Entry version history">{versions.map(version => <button key={version.revision} disabled={busy} onClick={() => showVersion(version.revision)}><span>Version {version.revision}{version.revision === (entry.current_revision || revision) ? ' · Current' : ''}<strong>{version.title || (version.kind === 'journal' ? 'Journal entry' : 'Quick note')}</strong></span><small>{new Date(version.saved_at).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}</small></button>)}</section>}
  </>
}
