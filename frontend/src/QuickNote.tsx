import { workspaceStorage, draftLocation } from './demoSession'
import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowRight, LoaderCircle, Plus, X } from 'lucide-react'
import EntryLimit, { ENTRY_CHARACTER_LIMIT, entryLength } from './EntryLimit'
import { api } from './api'
import { quickNoteDraftKey } from './writingDrafts'
import type { QuickNoteDraft } from './writingDrafts'

export default function QuickNote({draft, onChange, onSaved}: {draft: QuickNoteDraft; onChange: (draft: QuickNoteDraft) => void; onSaved: () => void}) {
  const [open, setOpen] = useState(false)
  const {text, title} = draft
  const [showTitle, setShowTitle] = useState(!!draft.title)
  const [stored, setStored] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const dialog = useRef<HTMLDialogElement>(null)
  const writing = useRef<HTMLTextAreaElement>(null)
  const id = useId()
  useEffect(() => {
    try {
      if (text || title) workspaceStorage.setItem(quickNoteDraftKey, JSON.stringify({text, title}))
      else workspaceStorage.removeItem(quickNoteDraftKey)
      setStored(true)
    } catch { setStored(false) }
  }, [text, title])
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const element = dialog.current!
    element.showModal(); writing.current?.focus()
    return () => { element.close(); previous?.focus() }
  }, [open])
  const save = async () => {
    if (saving || !text.trim() || entryLength(text) > ENTRY_CHARACTER_LIMIT) return
    setSaving(true); setError('')
    try {
      await api('/notes', 'POST', {text, title, kind: 'note', entry_date: null})
      onChange({text: '', title: ''}); setOpen(false); onSaved()
    } catch (err) { setError((err as Error).message) }
    finally { setSaving(false) }
  }
  return <>
    <button className="quick-note-trigger" aria-label="Quick note" title="Quick note" onClick={() => setOpen(true)}><Plus size={15} /><span>Quick note</span></button>
    {open && createPortal(<dialog ref={dialog} className="quick-note-dialog" aria-labelledby={`${id}-title`} onCancel={event => { if (saving) event.preventDefault(); else setOpen(false) }} onClick={event => {
      const box = event.currentTarget.getBoundingClientRect()
      if (!saving && event.target === event.currentTarget && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) setOpen(false)
    }}>
      <div className="modal-heading"><h2 id={`${id}-title`}>A quick thought.</h2><button className="icon-button" aria-label="Close quick note" disabled={saving} onClick={() => setOpen(false)}><X size={18} /></button></div>
      <p className="quick-note-description">Catch it before it slips away. Weaver will connect the details.</p>
      <form onSubmit={event => { event.preventDefault(); void save() }}>
        {showTitle ? (
          <label className="quick-note-title">Note title<input value={title} maxLength={180} disabled={saving} onChange={event => onChange({...draft, title: event.target.value})} /></label>
        ) : (
          <div className="quick-note-title-toggle"><button type="button" className="text-button" disabled={saving} onClick={() => setShowTitle(true)}>+ Add a title (optional)</button></div>
        )}
        <label className="sr-only" htmlFor={`${id}-writing`}>Your quick note</label>
        <textarea id={`${id}-writing`} ref={writing} value={text} aria-describedby={`${id}-limit`} aria-invalid={entryLength(text) > ENTRY_CHARACTER_LIMIT} disabled={saving} placeholder="What would you like to remember?" onChange={event => onChange({...draft, text: event.target.value})} />
        <EntryLimit text={text} id={`${id}-limit`} />
        {error && <p className="timing-error" role="alert">{error}</p>}
        <div className="quick-note-footer"><span className="draft-indicator" role="status">{text || title ? stored ? draftLocation() : 'Draft not backed up — keep this page open' : ''}</span><button className="primary" disabled={saving || !text.trim() || entryLength(text) > ENTRY_CHARACTER_LIMIT}>{saving ? <><LoaderCircle size={15} className="spin" /> Saving…</> : <>Save note <ArrowRight size={15} /></>}</button></div>
      </form>
    </dialog>, document.body)}
  </>
}
