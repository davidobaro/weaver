type ReminderSource = {person_id: number | null; person: string; value: string; category?: string}
type Reminder = {kind: string; title: string; sources: ReminderSource[]}

export function sentence(text: string) {
  const value = text.trim().replace(/\s+/g, ' ')
  if (!value) return ''
  const capitalized = value[0].toLocaleUpperCase() + value.slice(1)
  return /[.!?…]["”’']?$/.test(capitalized) ? capitalized : `${capitalized}.`
}

/** Display copy only: stored memories, quotes, scheduling and action IDs stay intact. */
export function reminderText(item: Reminder) {
  if (item.kind === 'connection') return item.title
  const source = item.sources[0]
  if (source.category === 'birthday') return sentence(`${item.title} — ${source.value}`)
  let value = source.value.trim()
  if (source.person_id !== null && source.person) {
    const name = source.person
    // Only resolve unambiguous direct objects. "Her sister" must remain her sister.
    value = value.replace(/^(ask)\s+(?:her|him|them)\b(?=\s+(?:about|how|if|whether|to)\b|[.!?]?$)/i, (_, verb) => `${verb} ${name}`)
      .replace(/^(send|give|show)\s+(?:her|him|them)\s+(?=(?:a|an|the|that|this|some)\b)/i, (_, verb) => `${verb} ${name} `)
      .replace(/^(ask)\s+(?=how\b|about\b)/i, (_, verb) => `${verb} ${name} `)
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    if (!new RegExp(`(^|[^\\p{L}\\p{N}_])${escaped}($|[^\\p{L}\\p{N}_])`, 'iu').test(value)) {
      value = `${name}: ${sentence(value)}`
    }
  }
  return sentence(value)
}
