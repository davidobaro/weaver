export const ENTRY_CHARACTER_LIMIT = 5000
export const entryLength = (text: string) => Array.from(text).length

export default function EntryLimit({ text, id }: { text: string; id: string }) {
  const length = entryLength(text)
  const remaining = ENTRY_CHARACTER_LIMIT - length
  return <p id={id} className={`entry-limit ${remaining < 0 ? 'over-limit' : ''}`}>
    <span>{length.toLocaleString()} / 5,000 characters</span>
    {remaining < 0 ? <span role="alert">Split this into separate entries or remove {(-remaining).toLocaleString()} characters to save. Your writing is still here.</span>
      : remaining === 0 ? <span>Entry limit reached. Start another entry to keep writing.</span>
      : remaining <= 500 ? <span>{remaining.toLocaleString()} characters left.</span> : null}
  </p>
}
