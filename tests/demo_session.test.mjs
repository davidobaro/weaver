import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from '../frontend/node_modules/typescript/lib/typescript.js'
let sequence=0
const token='A'.repeat(43), nextToken='B'.repeat(43)
function storage(values={}) {
  const result={...values}
  Object.defineProperties(result,{
    getItem:{value(key){return this[key]??null}},
    setItem:{value(key,value){this[key]=String(value)}},
    removeItem:{value(key){delete this[key]}},
  })
  return result
}
function transpile(file) {return ts.transpileModule(readFileSync(new URL(`../frontend/src/${file}`,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText}
const moduleUrl=source=>`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
async function fixture(t,{saved={},mode='demo',disabled=false,handler}={}) {
  const old={fetch:globalThis.fetch,window:globalThis.window,sessionStorage:Object.getOwnPropertyDescriptor(globalThis,'sessionStorage'),localStorage:Object.getOwnPropertyDescriptor(globalThis,'localStorage')}
  const session=storage(saved), local=storage({'weaver-journal-draft-v2':'private local draft'}),events=new EventTarget(),calls=[]
  globalThis.window=events
  Object.defineProperty(globalThis,'sessionStorage',{configurable:true,get(){if(disabled)throw new Error('blocked');return session}})
  Object.defineProperty(globalThis,'localStorage',{configurable:true,value:local})
  globalThis.fetch=async(path,options={})=>{
    calls.push({path,options})
    const answer=await handler?.(path,options)
    if(answer)return answer
    if(path==='/api/config')return Response.json({mode,idle_seconds:3600})
    if(path==='/api/session'&&options.method==='POST')return Response.json({token},{status:201})
    if(path==='/api/session'&&options.method==='DELETE')return new Response(null,{status:204})
    return Response.json({value:'current'})
  }
  t.after(()=>{
    globalThis.fetch=old.fetch;globalThis.window=old.window
    for(const name of ['sessionStorage','localStorage'])if(old[name])Object.defineProperty(globalThis,name,old[name]);else delete globalThis[name]
  })
  const url=moduleUrl(transpile('demoSession.ts')+`\n// instance ${++sequence}`)
  const sessionApi=await import(url)
  const api=await import(moduleUrl(transpile('api.ts').replace("'./demoSession'",JSON.stringify(url))))
  return {sessionApi,api,session,local,events,calls}
}

test('concurrent bootstrap creates one session and never imports private local drafts',async t=>{
  const {sessionApi:s,calls,local}=await fixture(t)
  await Promise.all([s.initializeSession(),s.initializeSession()])
  assert.equal(calls.filter(x=>x.path==='/api/session').length,1)
  assert.equal(s.workspaceStorage.getItem('weaver-journal-draft-v2'),null)
  s.workspaceStorage.setItem('weaver-journal-draft-v2','demo draft')
  assert.equal(local.getItem('weaver-journal-draft-v2'),'private local draft')
  assert.deepEqual(s.sessionAuthorization(),{Authorization:`Bearer ${token}`})
})

test('reload reuses a stored session without silently replacing an expired workspace',async t=>{
  const {sessionApi:s,calls}=await fixture(t,{saved:{'weaver-demo-token-v1':token}})
  await s.initializeSession()
  assert.equal(calls.length,1)
  assert.equal(s.sessionAuthorization().Authorization,`Bearer ${token}`)
})

test('local mode preserves local draft persistence and does not create a demo',async t=>{
  const {sessionApi:s,calls}=await fixture(t,{mode:'local'})
  await s.initializeSession()
  assert.equal(s.workspaceStorage.getItem('weaver-journal-draft-v2'),'private local draft')
  s.workspaceStorage.setItem('new','local')
  assert.deepEqual(s.sessionAuthorization(),{})
  assert.equal(calls.length,1)
})

test('reset revokes server workspace, clears session drafts, and preserves unrelated browser data',async t=>{
  let creations=0
  const {sessionApi:s,session,calls}=await fixture(t,{handler:(path,options)=>path==='/api/session'&&options.method==='POST'?Response.json({token:creations++?nextToken:token},{status:201}):undefined,saved:{unrelated:'keep'}})
  await s.initializeSession()
  s.workspaceStorage.setItem('entry-edit-1','old draft')
  s.workspaceStorage.setItem('weaver-notification-ack','old receipt')
  await s.resetDemoSession()
  assert.equal(s.workspaceStorage.getItem('entry-edit-1'),null)
  assert.equal(session.unrelated,'keep')
  assert.ok(!Object.keys(session).some(key=>key.includes(token+':')))
  assert.equal(s.sessionAuthorization().Authorization,`Bearer ${nextToken}`)
  assert.equal(calls.find(x=>x.options.method==='DELETE').options.headers.Authorization,`Bearer ${token}`)
})

test('failed reset does not discard a still-valid workspace or its unsent draft',async t=>{
  const {sessionApi:s}=await fixture(t,{handler:(path,options)=>options.method==='DELETE'?Response.json({detail:'Try later'},{status:503}):undefined})
  await s.initializeSession();s.workspaceStorage.setItem('draft','keep')
  await assert.rejects(s.resetDemoSession(),/Try later/)
  assert.equal(s.workspaceStorage.getItem('draft'),'keep')
  assert.equal(s.sessionAuthorization().Authorization,`Bearer ${token}`)
})

test('storage-unavailable mode keeps only in-memory session drafts',async t=>{
  const {sessionApi:s}=await fixture(t,{disabled:true})
  await s.initializeSession();s.workspaceStorage.setItem('draft','here')
  assert.equal(s.usesMemoryOnly(),true)
  assert.equal(s.workspaceStorage.getItem('draft'),'here')
  await s.resetDemoSession()
  assert.equal(s.workspaceStorage.getItem('draft'),null)
})

test('expired API response ends the session once, and subsequent mutations are never sent',async t=>{
  const {sessionApi:s,api,calls,events}=await fixture(t,{handler:path=>path==='/api/state'?Response.json({detail:'Session ended'},{status:401}):undefined})
  await s.initializeSession()
  let expired=0;events.addEventListener('weaver-session-ended',()=>expired++)
  await assert.rejects(api.api('/state'),/Session ended/)
  const count=calls.length
  await assert.rejects(api.api('/notes','POST',{text:'do not replay'}),/ended/)
  assert.equal(calls.length,count)
  assert.equal(expired,1)
})

test('late response from a replaced session cannot publish into the new UI state',async t=>{
  let finish
  const waiting=new Promise(resolve=>{finish=resolve})
  const {sessionApi:s,api}=await fixture(t,{handler:path=>path==='/api/state'?waiting:undefined})
  await s.initializeSession()
  const pending=api.api('/state')
  await s.resetDemoSession()
  finish(Response.json({notes:['old private writing']}))
  await assert.rejects(pending,/session changed/)
})

test('export downloads use session authorization without embedding the credential in a URL',async t=>{
  const {sessionApi:s,api,calls}=await fixture(t)
  await s.initializeSession()
  const oldDocument=globalThis.document
  let clicked=false
  globalThis.document={createElement:()=>({click(){clicked=true}})}
  globalThis.window.setTimeout=callback=>callback()
  t.after(()=>{globalThis.document=oldDocument})
  await api.exportWorkspace()
  const request=calls.find(x=>x.path==='/api/export')
  assert.equal(request.options.headers.Authorization,`Bearer ${token}`)
  assert.equal(clicked,true)
  assert.ok(calls.every(x=>!x.path.includes(token)))
})
