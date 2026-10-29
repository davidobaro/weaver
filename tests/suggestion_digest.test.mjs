import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from '../frontend/node_modules/typescript/lib/typescript.js'
const source=readFileSync(new URL('../frontend/src/suggestionDigest.ts',import.meta.url),'utf8')
const {outputText}=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}})
const {suggestionDigest,insightSections}=await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
const day='2026-10-28'
const item=(id,due_start=null,overdue=false)=>({id,due_start,overdue})

test('shows at most three entries while preserving supplied urgency order',()=>{
 const items=[item('overdue','2026-10-25',true),item('today',day),item('soon','2026-10-30'),item('undated')]
 const before=JSON.stringify(items)
 const result=suggestionDigest(items,day)
 assert.deepEqual(result.highlights.map(x=>x.id),['overdue','today','soon'])
 assert.equal(result.remaining,1)
 assert.equal(JSON.stringify(items),before)
})

test('distant repeats never displace near or undated work',()=>{
 const result=suggestionDigest([item('next-year','2027-04-01'),item('call'),item('birthday','2026-11-20')],day)
 assert.deepEqual(result.highlights.map(x=>x.id),['call'])
 assert.deepEqual(result.groups.map(g=>[g.key,g.items.map(x=>x.id)]),[['upcoming',['birthday']],['later',['next-year']]])
})

test('additional overdue tasks remain in needs-attention instead of later',()=>{
 const items=[1,2,3,4].map(id=>item(String(id),'2026-10-25',true))
 const result=suggestionDigest(items,day)
 assert.equal(result.groups[0].key,'attention')
 assert.equal(result.groups[0].items[0].id,'4')
})

test('all remaining suggestions are reachable exactly once',()=>{
 const items=[item('a'),item('b'),item('c'),item('d'),item('e','2026-11-01'),item('f','2027-03-01'),item('g',day)]
 const result=suggestionDigest(items,day)
 const ids=[...result.highlights,...result.groups.flatMap(g=>g.items)].map(x=>x.id)
 assert.equal(new Set(ids).size,items.length)
 assert.deepEqual(new Set(ids),new Set(items.map(x=>x.id)))
 assert.equal(result.remaining,result.groups.reduce((n,g)=>n+g.items.length,0))
})

test('cutoffs use calendar days across month and daylight-saving boundaries',()=>{
 const result=suggestionDigest([item('day14','2026-11-11'),item('day15','2026-11-12'),item('day30','2026-11-27'),item('day31','2026-11-28')],day)
 assert.deepEqual(result.highlights.map(x=>x.id),['day14'])
 assert.deepEqual(result.groups.find(g=>g.key==='upcoming').items.map(x=>x.id),['day15','day30'])
 assert.deepEqual(result.groups.find(g=>g.key==='later').items.map(x=>x.id),['day31'])
})

test('an empty or filtered feed does not retain old highlights',()=>{
 assert.deepEqual(suggestionDigest([],day),{highlights:[],groups:[],remaining:0})
 assert.deepEqual(suggestionDigest([item('others-only')],day).highlights.map(x=>x.id),['others-only'])
})

test('full Insights lists every dated obligation before undated ones, with connections separate',()=>{
 const items=[
  {...item('ask-stewy'),kind:'follow_up'},
  {...item('later','2027-04-01'),kind:'date'},
  {...item('today',day),kind:'date'},
  {...item('maya'),kind:'follow_up'},
  {...item('connection'),kind:'connection'},
 ]
 const before=JSON.stringify(items)
 const groups=insightSections(items)
 assert.deepEqual(groups.map(g=>[g.label,g.items.map(x=>x.id)]),[
  ['Dated',['today','later']],['Undated',['ask-stewy','maya']],['Connections',['connection']],
 ])
 assert.equal(groups.flatMap(g=>g.items).length,items.length)
 assert.equal(JSON.stringify(items),before)
 assert.deepEqual(insightSections([]),[])
 assert.deepEqual(insightSections([items[0]]).map(g=>g.label),['Undated'])
})
