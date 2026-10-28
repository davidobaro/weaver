import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from '../frontend/node_modules/typescript/lib/typescript.js'

const source = readFileSync(new URL('../frontend/src/writingDrafts.ts', import.meta.url), 'utf8')
const {outputText} = ts.transpileModule(source, {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022}})
const {readWritingDrafts, journalDraftKey, quickNoteDraftKey} = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
const oldKey = 'weaver-writing-draft-v1'
const today = '2026-10-27'
function fixture(values = {}) {
  const saved = new Map(Object.entries(values).map(([key, value]) => [key, JSON.stringify(value)]))
  const storage = {getItem: key => saved.get(key) ?? null, setItem: (key, value) => saved.set(key, value), removeItem: key => saved.delete(key)}
  return {saved, storage}
}

test('fresh writing space is an empty journal plus an independent empty quick note', () => {
  const {storage} = fixture()
  assert.deepEqual(readWritingDrafts(today, storage), {journal: {text: '', title: '', entryDate: today}, quick: {text: '', title: ''}})
})

test('legacy journal draft preserves its text, title, date, and survives repeated initialization', () => {
  const {saved, storage} = fixture({[oldKey]: {kind: 'journal', text: 'A long reflection', title: 'Sunday', entryDate: '2026-10-25'}})
  const first = readWritingDrafts(today, storage)
  assert.deepEqual(first.journal, {text: 'A long reflection', title: 'Sunday', entryDate: '2026-10-25'})
  assert.equal(first.quick.text, '')
  assert.equal(saved.has(oldKey), false)
  assert.deepEqual(readWritingDrafts(today, storage), first)
})

test('legacy quick note goes to the popup and cannot become a journal draft', () => {
  const {saved, storage} = fixture({[oldKey]: {kind: 'note', text: 'Ask Mira about the book', title: 'A reminder'}})
  const result = readWritingDrafts(today, storage)
  assert.equal(result.journal.text, '')
  assert.deepEqual(result.quick, {text: 'Ask Mira about the book', title: 'A reminder'})
  assert.equal(saved.has(quickNoteDraftKey), true)
  assert.equal(saved.has(oldKey), false)
})

test('saving or clearing one draft cannot clear the other', () => {
  const {saved, storage} = fixture({[journalDraftKey]: {text: 'Journal in progress', title: '', entryDate: today}, [quickNoteDraftKey]: {text: 'A passing thought', title: ''}})
  storage.removeItem(quickNoteDraftKey)
  assert.equal(readWritingDrafts(today, storage).journal.text, 'Journal in progress')
  assert.equal(saved.has(journalDraftKey), true)
  storage.setItem(quickNoteDraftKey, JSON.stringify({text: 'Another thought', title: ''}))
  storage.removeItem(journalDraftKey)
  assert.equal(readWritingDrafts(today, storage).quick.text, 'Another thought')
})

test('existing destination wins and the old copy is preserved without resurrecting after save', () => {
  const {saved, storage} = fixture({[oldKey]: {kind: 'note', text: 'Older draft'}, [quickNoteDraftKey]: {text: 'Newer draft', title: ''}})
  assert.equal(readWritingDrafts(today, storage).quick.text, 'Newer draft')
  assert.equal(saved.has('weaver-writing-draft-legacy-backup-v1'), true)
  storage.removeItem(quickNoteDraftKey)
  assert.equal(readWritingDrafts(today, storage).quick.text, '')
})

test('failed migration retains the legacy copy and still recovers its writing in memory', () => {
  const {saved, storage} = fixture({[oldKey]: {kind: 'note', text: 'Do not lose this'}})
  storage.setItem = () => { throw new Error('Storage full') }
  assert.equal(readWritingDrafts(today, storage).quick.text, 'Do not lose this')
  assert.equal(saved.has(oldKey), true)
})

test('malformed stored data does not prevent writing or copy invalid fields into the editor', () => {
  const {saved, storage} = fixture({[journalDraftKey]: {text: 12, title: {}, entryDate: 'invalid'}})
  saved.set(quickNoteDraftKey, 'broken JSON')
  assert.deepEqual(readWritingDrafts(today, storage), {journal: {text: '', title: '', entryDate: today}, quick: {text: '', title: ''}})
})
