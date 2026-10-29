type DatedSuggestion = {id: string; due_start: string | null; overdue: boolean}

/** The full Insights page exposes every open item; the journal keeps its digest. */
export function insightSections<T extends DatedSuggestion & {kind: string}>(items: T[]) {
  return [
    {key:'dated',label:'Dated',items:items.filter(item=>item.kind!=='connection' && !!item.due_start)
      .sort((a,b)=>a.due_start!.localeCompare(b.due_start!))},
    {key:'undated',label:'Undated',items:items.filter(item=>item.kind!=='connection' && !item.due_start)},
    {key:'connections',label:'Connections',items:items.filter(item=>item.kind==='connection')},
  ].filter(group=>group.items.length)
}
const after = (today: string, days: number) => {
  const day = new Date(`${today}T12:00:00Z`)
  day.setUTCDate(day.getUTCDate() + days)
  return day.toISOString().slice(0,10)
}

/** Preserve server priority, with distant dates kept out of the initial digest. */
export function suggestionDigest<T extends DatedSuggestion>(items: T[], today: string) {
  const fortnight=after(today,14), month=after(today,30)
  const highlights=items.filter(item=>item.overdue || !item.due_start || item.due_start<=fortnight).slice(0,3)
  const selected=new Set(highlights.map(item=>item.id))
  const others=items.filter(item=>!selected.has(item.id))
  const groups=[
    {key:'attention',label:'More needing attention',items:others.filter(item=>item.overdue || !!item.due_start && item.due_start<=today)},
    {key:'upcoming',label:'Upcoming',items:others.filter(item=>!item.overdue && !!item.due_start && item.due_start>today && item.due_start<=month)},
    {key:'anytime',label:'Anytime',items:others.filter(item=>!item.overdue && !item.due_start)},
    {key:'later',label:'Later',items:others.filter(item=>!item.overdue && !!item.due_start && item.due_start>month)},
  ].filter(group=>group.items.length)
  return {highlights,groups,remaining:others.length}
}
