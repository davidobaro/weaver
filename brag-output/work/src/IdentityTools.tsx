import { useState } from 'react'
import { GitMerge, Plus, RotateCcw, X } from 'lucide-react'
import { api } from './api'

export type Alias = { name: string; name_key: string }
export type Match = { source_id: number; source_name: string; target_id: number; target_name: string }
export type Merge = { id: string; target_id: number; source_name: string; can_undo: boolean }
type IdentityPerson = { id: number; name: string; aliases?: Alias[] }

export function IdentityQuestion({ match, onChanged }: { match: Match; onChanged: (personId?: number) => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const answer = async (same: boolean) => {
    setBusy(true); setError('')
    try {
      const result = await api<{ person_id?: number }>(same ? '/people/merge' : '/people/distinct', 'POST', {source_id: match.source_id, target_id: match.target_id})
      await onChanged(result.person_id)
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  return <section className="identity-question" aria-label="Possible duplicate person"><div><h2>Is {match.source_name} the same person as {match.target_name}?</h2><p>If so, keep {match.target_name} as the profile name and {match.source_name} as an alias. All notes and memories stay together.</p>{error && <p className="note-error" role="alert">{error}</p>}</div><div className="identity-question-actions"><button className="small-button" disabled={busy} onClick={() => answer(true)}>Same person</button><button className="text-button" disabled={busy} onClick={() => answer(false)}>Different people</button></div></section>
}

export default function IdentityTools({ person, people, merges, onChanged }: {
  person: IdentityPerson; people: IdentityPerson[]; merges: Merge[]; onChanged: (personId?: number) => Promise<void>
}) {
  const [alias, setAlias] = useState('')
  const [target, setTarget] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const mutate = async (path: string, method: string, body?: unknown, message?: string) => {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api<{person_id?: number} | undefined>(path, method, body)
      setAlias(''); setTarget(''); await onChanged(result?.person_id)
      if (message) setNotice(message)
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  const targetPerson = people.find(p => p.id === Number(target))
  return <details className="identity-tools"><summary>Names & profiles</summary><div className="identity-tools-body">
    <p className="identity-hint">Confirmed aliases connect future notes automatically.</p>
    {!!person.aliases?.length && <div className="alias-list">{person.aliases.map(name => <span key={name.name_key}>{name.name}<button disabled={busy} aria-label={`Remove alias ${name.name}`} onClick={() => mutate(`/people/${person.id}/aliases`, 'DELETE', {name: name.name}, 'Alias removed. Existing memories are unchanged.')}><X size={12} /></button></span>)}</div>}
    <form className="alias-form" onSubmit={event => { event.preventDefault(); if (alias.trim()) void mutate(`/people/${person.id}/aliases`, 'POST', {name: alias}, 'Alias saved. Future notes using that name will join this profile.') }}><label className="sr-only" htmlFor={`alias-${person.id}`}>Add an alias for {person.name}</label><input id={`alias-${person.id}`} maxLength={120} value={alias} onChange={event => setAlias(event.target.value)} placeholder="A nickname or another name…" disabled={busy} /><button className="small-button" disabled={busy || !alias.trim()}><Plus size={13} /> Add alias</button></form>
    {people.length > 1 && <div className="merge-controls"><label htmlFor={`merge-${person.id}`}>Merge {person.name} into another profile</label><select id={`merge-${person.id}`} value={target} onChange={event => setTarget(event.target.value)} disabled={busy}><option value="">Choose a profile…</option>{people.filter(p => p.id !== person.id).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>{targetPerson && <><p>Keep <strong>{targetPerson.name}</strong> as the name. {person.name} becomes an alias; both profiles’ notes and memory history are preserved.</p><button className="small-button" disabled={busy} onClick={() => mutate('/people/merge', 'POST', {source_id: person.id, target_id: targetPerson.id})}><GitMerge size={13} /> Merge into {targetPerson.name}</button></>}</div>}
    {merges.filter(m => m.target_id === person.id).map(merge => <div className="merge-event" key={merge.id}><span>Merged {merge.source_name} into {person.name}</span>{merge.can_undo ? <button className="text-button" disabled={busy} onClick={() => mutate(`/people/merges/${merge.id}/undo`, 'POST')}><RotateCcw size={12} /> Undo merge</button> : <small>Profile updated since merging. Use Edit on a memory to move it.</small>}</div>)}
    {error && <p className="note-error" role="alert">{error}</p>}{notice && <p className="identity-hint" role="status">{notice}</p>}
  </div></details>
}
