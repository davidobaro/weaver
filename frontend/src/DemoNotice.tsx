import { RotateCcw } from 'lucide-react'
import { isDemo, requestDemoReset, usesMemoryOnly } from './demoSession'

export default function DemoNotice() {
  if (!isDemo()) return null
  return <aside className="demo-notice" aria-label="Temporary demo"><p><strong>Temporary demo.</strong> Writing clears after inactivity or a server restart. Use fictional details; entries are processed by Nebius.{usesMemoryOnly() && ' Browser storage is unavailable; refreshing starts a new session.'}</p><button type="button" className="source-link" onClick={()=>{if(window.confirm('Clear this demo workspace and its drafts? Export anything you want to keep first.'))requestDemoReset()}}><RotateCcw size={13}/> Reset demo</button></aside>
}
