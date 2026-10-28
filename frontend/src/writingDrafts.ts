export const journalDraftKey = 'weaver-journal-draft-v2'
export const quickNoteDraftKey = 'weaver-quick-note-draft-v1'
const legacyKey = 'weaver-writing-draft-v1'
export type JournalDraft = {text: string; title: string; entryDate: string}
export type QuickNoteDraft = {text: string; title: string}
type DraftStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

/** Move the old shared draft into its own writing surface without losing it. */
export function readWritingDrafts(today: string, suppliedStorage?: DraftStorage): {journal: JournalDraft; quick: QuickNoteDraft} {
  const empty = {journal: {text: '', title: '', entryDate: today}, quick: {text: '', title: ''}}
  let storage: DraftStorage
  try { storage = suppliedStorage || localStorage } catch { return empty }
  const read = (key: string): Record<string, unknown> | null => {
    try {
      const value = JSON.parse(storage.getItem(key) || 'null')
      return value && typeof value === 'object' && !Array.isArray(value) ? value : null
    } catch { return null }
  }
  const legacy = read(legacyKey)
  const savedJournal = read(journalDraftKey)
  const savedQuick = read(quickNoteDraftKey)
  const journal = savedJournal || (legacy?.kind === 'journal' ? legacy : {})
  const quick = savedQuick || (legacy && legacy.kind !== 'journal' ? legacy : {})
  const content = (value: Record<string, unknown>) => ({text: typeof value.text === 'string' ? value.text : '', title: typeof value.title === 'string' ? value.title : ''})
  const result = {journal: {...content(journal), entryDate: typeof journal.entryDate === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(journal.entryDate) ? journal.entryDate : today}, quick: content(quick)}
  if (legacy) {
    try {
      // Only remove the legacy copy once its destination has been written.
      if (legacy.kind === 'journal' && !savedJournal) storage.setItem(journalDraftKey, JSON.stringify(result.journal))
      if (legacy.kind !== 'journal' && !savedQuick) storage.setItem(quickNoteDraftKey, JSON.stringify(result.quick))
      // Preserve a conflicting legacy copy without letting it reappear when a
      // newer draft is intentionally cleared or saved.
      if (legacy.kind === 'journal' ? !!savedJournal : !!savedQuick) {
        storage.setItem('weaver-writing-draft-legacy-backup-v1', JSON.stringify(legacy))
      }
      storage.removeItem(legacyKey)
    } catch { /* The recovered draft remains available in this session. */ }
  }
  return result
}
