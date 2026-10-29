import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from '../frontend/node_modules/typescript/lib/typescript.js'
const {outputText}=ts.transpileModule(readFileSync(new URL('../frontend/src/reminderText.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}})
const {reminderText,sentence}=await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
const item=(value,person='Maya',extra={})=>({kind:'follow_up',title:'Check in',sources:[{person_id:person?1:null,person,value,...extra}]})

test('exported reminders show names, context and punctuation',()=>{
 assert.equal(reminderText(item('send her that beginner ceramics class by Friday')), 'Send Maya that beginner ceramics class by Friday.')
 assert.equal(reminderText(item('ask about the book when we next talk')), 'Ask Maya about the book when we next talk.')
 assert.equal(reminderText(item('ask how the trip went afterward','Stewy')), 'Ask Stewy how the trip went afterward.')
 assert.equal(reminderText(item('ask her about the book when we next talk')), 'Ask Maya about the book when we next talk.')
})
test('ambiguous possessives keep their meaning and get explicit person context',()=>{
 assert.equal(reminderText(item('send her sister a card')), 'Maya: Send her sister a card.')
 assert.equal(reminderText(item('ask her sister about the trip')), 'Maya: Ask her sister about the trip.')
 assert.equal(reminderText(item('trip to Vermont next month','Stewy')), 'Stewy: Trip to Vermont next month.')
})
test('personal copy and existing punctuation are preserved',()=>{
 assert.equal(reminderText(item('pay the electricity bill tomorrow',null)), 'Pay the electricity bill tomorrow.')
 assert.equal(sentence('Ask Maya about the book?'), 'Ask Maya about the book?')
 assert.equal(sentence('Ask Maya about the book.'), 'Ask Maya about the book.')
 assert.equal(sentence('  book a dentist appointment sometime next week  '), 'Book a dentist appointment sometime next week.')
})
test('names are matched literally without confusing substrings or rewriting quotes',()=>{
 const reminder=item('send her that guide','Ann')
 const original=JSON.stringify(reminder)
 assert.equal(reminderText(reminder),'Send Ann that guide.')
 assert.equal(JSON.stringify(reminder),original)
 assert.equal(reminderText(item('ask Anna about the book','Ann')), 'Ann: Ask Anna about the book.')
 assert.equal(reminderText(item('ask D’Arcy about the book','D’Arcy')), 'Ask D’Arcy about the book.')
})
test('birthday uses its named headline rather than showing an unexplained date',()=>{
 const birthday=item('November 12','Maya',{category:'birthday'})
 birthday.title='Make room for Maya’s birthday'
 assert.equal(reminderText(birthday),'Make room for Maya’s birthday — November 12.')
})
