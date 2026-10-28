export type EntryKind = 'note' | 'journal'
export type Entry = {
  id: number; kind?: EntryKind; title?: string; entry_date?: string | null;
  text: string; status: string; candidates: { person: string; category: 'birthday' | 'interest' | 'plan' | 'commitment' | 'relationship' | 'context'; value: string; evidence: string }[] | null;
  error: string | null; created_at: string; revision?: number; current_revision?: number;
  updated_at?: string | null; is_history?: boolean;
  noticed?: {counts: {people: number; facts: number; tasks: number; completed: number}; version: string} | null;
}
export const entryDate = (value: string) => new Date(value.length === 10 ? `${value}T12:00:00` : value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
