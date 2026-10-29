import { useEffect, useState } from 'react'
import App from './App'
import { api } from './api'
import { initializeSession, isDemo, resetDemoSession, sessionGeneration, sessionIsEnded } from './demoSession'
import Wordmark from './Wordmark'
import { LoaderCircle } from 'lucide-react'

export default function SessionApp() {
  const [state,setState]=useState<'loading'|'ready'|'ended'|'error'>('loading')
  const [error,setError]=useState('')
  const [generation,setGeneration]=useState(0)
  const [retry,setRetry]=useState(0)
  useEffect(()=>{
    let active=true
    void initializeSession().then(()=>{if(active)setState('ready')}).catch(err=>{if(active){setError(err.message);setState('error')}})
    return ()=>{active=false}
  },[retry])
  useEffect(()=>{
    let working=false
    const expired=()=>setState('ended')
    const reset=async()=>{
      if (working) return
      working=true
      setState('loading');setError('')
      try { await resetDemoSession();setGeneration(sessionGeneration());setState('ready') }
      catch(err) {setError((err as Error).message);setState(sessionIsEnded()?'ended':'error')}
      finally {working=false}
    }
    window.addEventListener('weaver-session-ended',expired)
    window.addEventListener('weaver-reset-demo',reset)
    return ()=>{window.removeEventListener('weaver-session-ended',expired);window.removeEventListener('weaver-reset-demo',reset)}
  },[])
  useEffect(()=>{
    if (state !== 'ready' || !isDemo()) return
    let last=0
    const activity=(event:Event)=>{
      if (!event.isTrusted || Date.now()-last < 30000) return
      last=Date.now()
      void api('/session/activity','POST').catch(()=>{})
    }
    window.addEventListener('pointerdown',activity,true)
    window.addEventListener('keydown',activity,true)
    return ()=>{window.removeEventListener('pointerdown',activity,true);window.removeEventListener('keydown',activity,true)}
  },[state,generation])
  if (state==='ready') return <App key={generation}/>
  return <main className="demo-session-screen"><div className="brand"><Wordmark/></div>{state==='loading'?<p role="status"><LoaderCircle size={17} className="spin"/> Opening your workspace…</p>:<><h1>{state==='ended'?'Your temporary session has ended.':'Weaver couldn’t open the workspace.'}</h1><p>{state==='ended'?'Demo writing is temporary. Start a fresh workspace to continue.':error}</p>{state==='ended' && error && <p role="alert">{error}</p>}<button className="primary" onClick={()=>state==='ended'?window.dispatchEvent(new Event('weaver-reset-demo')):(setState('loading'),setRetry(value=>value+1))}>{state==='ended'?'Start a new demo':'Try again'}</button></>}</main>
}
