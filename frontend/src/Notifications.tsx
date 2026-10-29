import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Bell, X } from 'lucide-react'
import { api } from './api'
import { deliverReminders } from './notificationDelivery'

const storageKey = 'weaver-notifications'
type Settings = { enabled: boolean; device: string }
const supported = typeof Notification !== 'undefined' && window.isSecureContext
function readSettings(): Settings | null {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || 'null')
    return value && typeof value.enabled === 'boolean' && typeof value.device === 'string' ? value : null
  } catch { return null }
}

export default function Notifications({ revision, onOpen }: { revision: unknown; onOpen: () => void }) {
  const [settings, setSettings] = useState(readSettings)
  const [permission, setPermission] = useState(supported ? Notification.permission : 'default')
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const openFeed = useRef(onOpen)
  openFeed.current = onOpen

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    dialog.current?.showModal()
    return () => { dialog.current?.close(); previous?.focus() }
  }, [open])

  useEffect(() => {
    const stored = (event: StorageEvent) => { if (event.key === storageKey || event.key === null) { setSettings(readSettings()); setError('') } }
    window.addEventListener('storage', stored)
    return () => window.removeEventListener('storage', stored)
  }, [])

  useEffect(() => {
    if (!supported || !settings?.enabled || error) return
    let cancelled = false
    let checking = false
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York'
    const check = async () => {
      setPermission(Notification.permission)
      if (cancelled || checking || Notification.permission !== 'granted' || !readSettings()?.enabled) return
      checking = true
      try {
        await deliverReminders({
          storage: localStorage,
          active: () => !cancelled && !!readSettings()?.enabled,
          permitted: () => Notification.permission === 'granted',
          request: api,
          show: count => {
            const notification = new Notification('A little attention from Weaver', {
              body: `${count} reminder${count === 1 ? '' : 's'} ready to revisit. Open Insights to see the details.`,
              tag: 'weaver-reminders',
            })
            notification.onclick = () => { window.focus(); openFeed.current(); notification.close() }
            notification.onerror = () => { if (!cancelled) setError('Your browser could not show an alert. Check its notification settings and your device’s notification permissions.') }
          },
        }, settings.device, timezone)
      } catch (err) {
        // Network failures retry quietly; unsupported constructors need user action.
        if (!cancelled && err instanceof TypeError && !String(err.message).includes('fetch')) setError('Alerts are unavailable in this browser. Try a desktop browser with notifications enabled.')
      } finally { checking = false }
    }
    void check()
    const timer = window.setInterval(check, 60000)
    window.addEventListener('focus', check)
    window.addEventListener('weaver-suggestions-changed', check)
    return () => { cancelled = true; window.clearInterval(timer); window.removeEventListener('focus', check); window.removeEventListener('weaver-suggestions-changed', check) }
  }, [settings, revision, error])

  const enable = async () => {
    if (!supported) return
    setBusy(true); setError('')
    try {
      // Keep the permission request directly inside this explicit click handler.
      const result = await Notification.requestPermission()
      setPermission(result)
      if (result === 'granted') {
        const next = {device: settings?.device || crypto.randomUUID(), enabled: true}
        localStorage.setItem(storageKey, JSON.stringify(next)); setSettings(next)
      }
    } catch { setError('Could not enable alerts. Allow browser storage and notifications, then try again.') }
    finally { setBusy(false) }
  }
  const disable = () => {
    try {
      const next = {...settings!, enabled: false}
      localStorage.setItem(storageKey, JSON.stringify(next)); setSettings(next); setError('')
    } catch { setError('Could not save your preference. Check browser storage settings.') }
  }
  const enabled = !!settings?.enabled && permission === 'granted'
  return <>
    <button className="notification-button icon-button" aria-label="Reminder notifications" title="Reminder notifications" onClick={() => { setPermission(supported ? Notification.permission : 'default'); setOpen(true) }}><Bell size={16} />{enabled && <i />}</button>
    {open && createPortal(<dialog className="timing-dialog notification-dialog" ref={dialog} aria-labelledby="notifications-title" onCancel={() => setOpen(false)} onClick={event => {
      const bounds = event.currentTarget.getBoundingClientRect()
      if (event.target === event.currentTarget && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) setOpen(false)
    }}>
      <div className="notification-heading"><Bell size={19} /><h2 id="notifications-title">A gentle nudge</h2><button className="icon-button" aria-label="Close notifications" onClick={() => setOpen(false)}><X size={18} /></button></div>
      <p>Get an alert when a reminder is due or a snoozed item returns. Overdue reminders are included when you return.</p>
      <p>Works while Weaver is open in this browser. Alerts show a count, keeping your writing private.</p>
      <div className="notification-state" role="status">{!supported ? 'Notifications aren’t supported here. Try a desktop browser on localhost or HTTPS.' : permission === 'denied' ? 'Notifications are blocked. Allow them in your browser’s site settings to turn alerts on.' : enabled ? 'Alerts are on for this browser.' : 'Alerts are off.'}</div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="notification-footer">{settings?.enabled ? <button className="small-button" onClick={disable}>Turn off alerts</button> : <button className="primary" disabled={!supported || permission === 'denied' || busy} onClick={() => void enable()}>{busy ? 'Enabling…' : 'Enable alerts'}</button>}{error && enabled && <button className="text-button" onClick={() => setError('')}>Try again</button>}</div>
    </dialog>, document.body)}
  </>
}
