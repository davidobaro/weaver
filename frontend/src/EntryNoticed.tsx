import { useEffect, useState } from 'react'
import { ArrowUpRight, ChevronDown, LoaderCircle, Sparkles } from 'lucide-react'
import { api } from './api'
import type { Entry } from './entries'

type NoticedItem = {kind: 'fact' | 'task' | 'completed'; person_id: number | null; person: string; category: string; value: string; evidence: string; active: boolean}
type Noticed = {people: {id: number; name: string}[]; items: NoticedItem[]}
const labels: Record<string,string> = {birthday:'Birthday',interest:'Interest',context:'Background',relationship:'Connection',plan:'Plan',commitment:'Commitment',task:'Task',reminder:'Reminder',goal:'Goal',completed:'Completed action'}

export default function EntryNoticed({entry,onPerson,onSource}: {entry: Entry; onPerson:(id:number)=>void; onSource:()=>void}) {
  const [open,setOpen]=useState(false)
  const [result,setResult]=useState<Noticed|null>(null)
  const [error,setError]=useState('')
  const [retry,setRetry]=useState(0)
  const version=entry.noticed?.version
  useEffect(()=>{
    if (!open || !version) return
    let cancelled=false
    setResult(null);setError('')
    api<Noticed>(`/notes/${entry.id}/noticed`).then(value=>{if(!cancelled)setResult(value)}).catch(err=>{if(!cancelled)setError(err.message)})
    return ()=>{cancelled=true}
  },[open,entry.id,version,retry])
  if (!entry.noticed) return null
  const counts=entry.noticed.counts
  const parts=[counts.people && `${counts.people} ${counts.people===1?'person':'people'}`,counts.facts && `${counts.facts} ${counts.facts===1?'fact':'facts'}`,counts.tasks && `${counts.tasks} ${counts.tasks===1?'task':'tasks'}`,counts.completed && `${counts.completed} ${counts.completed===1?'completed action':'completed actions'}`].filter(Boolean)
  return <details className="entry-noticed" onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary><Sparkles size={12} aria-hidden="true"/><span className="noticed-counts">{parts.join(' · ') || 'Just your writing'}</span><ChevronDown size={12} aria-hidden="true"/></summary>
    <div className="noticed-body">
      {error ? <p className="note-error" role="alert">Couldn’t load the details. <button className="text-button" onClick={()=>setRetry(value=>value+1)}>Retry</button></p> : !result ? <p className="noticed-loading" role="status"><LoaderCircle size={12} className="spin"/> Loading details…</p> : <>
        {!!result.people.length && <div className="noticed-people">{result.people.map(person=><button key={person.id} onClick={()=>onPerson(person.id)}>{person.name}<ArrowUpRight size={11}/></button>)}</div>}
        {!result.items.length && <p className="noticed-empty">No people or actionable details were extracted from this version. Your writing is saved.</p>}
        {result.items.map((item,index)=><div className="noticed-item" key={index}>
          <div className="noticed-item-label">{item.person} · {labels[item.category] || item.category}{!item.active && <span>Updated later</span>}</div>
          <p>{item.value}</p><blockquote>“{item.evidence}”</blockquote>
        </div>)}
        {!!result.items.length && <p className="noticed-explanation">Extracted from this version. Task status and schedules are managed in Insights.</p>}
        <button className="source-link" onClick={onSource}>Read or edit entry <ArrowUpRight size={11}/></button>
      </>}
    </div>
  </details>
}
