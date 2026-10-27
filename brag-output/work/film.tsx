import React from 'react'
import {createRoot} from 'react-dom/client'
import {flushSync} from 'react-dom'
import App from './src/App'
import Wordmark from './src/Wordmark'
import WovenThreads from './src/WovenThreads'
import './src/style.css'
import './film.css'
const root=createRoot(document.getElementById('film')!)
const entry='Nora loves ceramics.\nI need to renew my passport.\nSend Leo the recipe.'
const memory={id:1,note_id:1,note_revision:1,person:'Nora',category:'interest',value:'Loves ceramics',evidence:'Nora loves ceramics.',active:1,edited:0,replaces_id:null}
const nora={id:1,name:'Nora',aliases:[],memories:[memory],about:{note_count:1,facts:[{memory_id:1,note_id:1,note_revision:1,label:'Things they love',value:'Loves ceramics',evidence:'Nora loves ceramics.',noted_at:'2026-10-15',edited:false}]}}
const leo={id:2,name:'Leo',aliases:[],memories:[{...memory,id:2,person:'Leo',category:'commitment',value:'Send Leo the recipe',evidence:'Send Leo the recipe.'}],about:{note_count:1,facts:[]}}
const source={id:3,person_id:null,person:'You',note_id:1,note_revision:1,category:'task',value:'Renew my passport',evidence:'I need to renew my passport.',edited:0}
const task={id:'personal-3',scope:'personal',category:'task',kind:'follow_up',title:'Renew my passport',why:'A task from your writing.',sources:[source],due_start:null,due_end:null,overdue:false,status:'open'}
const ease=(v:number)=>{v=Math.max(0,Math.min(1,v));return v*v*(3-2*v)}
const ranges=[0,3,9.2,14,19.2,22.2]
function Brand(){return <div className="brand film-brand"><WovenThreads/><Wordmark/></div>}
function Film({t}:{t:number}){
 let sc=ranges.findIndex((v,i)=>i<5&&t>=v&&t<ranges[i+1]);if(sc<0)sc=4
 const local=t-ranges[sc],dur=ranges[sc+1]-ranges[sc]
 const a=Math.min(ease(local/.38),ease((dur-local)/.26))
 const complete=sc===3&&local>=2.4
 const typed=sc===1?entry.slice(0,Math.round(entry.length*ease((local-.3)/1.15))):''
 ;(window as any).__film={view:sc===2||sc===3?'people':'notes',personId:sc===2?1:0,draft:{text:typed,title:sc===1?'The little things':'',kind:'journal',entryDate:'2026-10-15'},data:{notes:sc===1?[]:[{id:1,text:entry,title:'The little things',kind:'journal',entry_date:'2026-10-15',created_at:'2026-10-15',status:'organized',revision:1}],people:sc===1?[]:[nora,leo],inference_configured:true,model:''},feed:{suggestions:sc===1?[]:[{...task,status:complete?'done':'open',...(complete?{completion:{note_id:2,note_revision:1,evidence:'I renewed my passport.'}}:{})}],today:'2026-10-15',timezone:'America/New_York'}}
 return <div className={'canvas scene-'+sc+(sc===1&&local>5.05?' has-save':'')}>
 <div className="paper-glow"/>
 <div className="corner"><Brand/><span>JOURNAL & NOTES</span></div>
 <div className="scene" style={{opacity:a,transform:'translateY('+((1-a)*18)+'px)'}}>
 {sc===0?<div className="intro"><div className="big-symbol"><WovenThreads/></div><h1>Your day.<br/><em>All its loose ends.</em></h1><p>A journal that connects the details.</p><div className="fine-rule"/></div>:sc===4?<div className="outro"><Brand/><h1>Write a little.<br/><em>Remember more.</em></h1><p>Woven from the moments that matter.</p></div>:<>
 <div className="scene-heading"><p className="scene-num">0{sc} / 03</p><h1>{sc===1?'Write it once.':sc===2?'Remember their little details.':'Keep track of your own, too.'}</h1><span>{sc===1?'JOURNAL':sc===2?'PEOPLE':'YOU'}</span></div>
 <div className={'product-window '+(complete?'is-complete':'')} style={{transform:'translateY('+((1-ease(local/.7))*25)+'px)'}}>
 <div className="window-bar"><i/><i/><i/><span>weaver · personal workspace</span></div>
 <div className="app-viewport"><div className="real-app"><App key={sc+'-'+t.toFixed(4)}/></div></div>
 {sc===1&&local>5.05&&<div className="saved-cue" style={{opacity:ease((local-5.05)/.2)}}>✓ &nbsp;Saved. Weaver connects the details.</div>}
 {sc===3&&local>1.15&&<div className="new-writing" style={{opacity:ease((local-1.15)/.4),transform:'translateY('+((1-ease((local-1.15)/.4))*15)+'px)'}}><span>FROM A LATER ENTRY</span><p>“I renewed my passport.”</p><b>{complete?'✓  Done from your writing':'Connecting the details…'}</b></div>}
 </div>
 </>}
 </div>
 <div className="bottom-line"><span>Write for yourself. Weaver connects the details.</span><span>{sc===0?'A PLACE FOR YOUR DAYS':sc===4?'WEAVER':'FICTIONAL DEMO ENTRIES'}</span></div>
 </div>
}
;(window as any).renderFrame=(t:number)=>{flushSync(()=>root.render(<Film t={t}/>));document.querySelectorAll('.suggestion-history').forEach(x=>{(x as HTMLDetailsElement).open=true})}
;(window as any).renderFrame(0.7)
