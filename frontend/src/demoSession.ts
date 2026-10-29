type Config = {mode: 'local' | 'demo'; idle_seconds: number | null}
const tokenKey = 'weaver-demo-token-v1'
let config: Config = {mode: 'local', idle_seconds: null}
let credential = ''
let ended = false
let generation = 0
let memoryOnly = false
let bootstrap: Promise<Config> | null = null
const memory = new Map<string, string>()
export const isDemo = () => config.mode === 'demo'
export const sessionGeneration = () => generation
export const sessionIsEnded = () => ended
export const usesMemoryOnly = () => memoryOnly
export const sessionAuthorization = (): Record<string,string> => isDemo() && credential ? {Authorization: `Bearer ${credential}`} : {}

async function body<T>(response: Response): Promise<T> {
  const value = await response.json().catch(()=>null)
  if (!response.ok) throw new Error(typeof value?.detail === 'string' ? value.detail : 'The demo could not start. Please try again.')
  return value as T
}
async function create() {
  const session = await body<{token: string}>(await fetch('/api/session',{method:'POST'}))
  credential = session.token
  ended = false
  try { sessionStorage.setItem(tokenKey, credential) } catch { memoryOnly = true }
}
export function initializeSession(): Promise<Config> {
  if (!bootstrap) bootstrap = (async()=>{
    config = await body<Config>(await fetch('/api/config', {cache:'no-store'}))
    if (isDemo()) {
      try { credential = sessionStorage.getItem(tokenKey) || '' } catch { memoryOnly = true }
      if (!credential) await create()
    }
    return config
  })().catch(error=>{bootstrap=null;throw error})
  return bootstrap
}
export function expireSession(expectedGeneration: number) {
  if (!isDemo() || generation !== expectedGeneration || ended) return
  ended = true
  generation++
  window.dispatchEvent(new Event('weaver-session-ended'))
}
export async function resetDemoSession() {
  if (!isDemo()) return
  const headers = sessionAuthorization()
  // Revoke first; a failed network request must not silently leave an old session active.
  if (credential) {
    const response = await fetch('/api/session', {method:'DELETE', headers})
    if (!response.ok && response.status !== 401) await body(response)
  }
  const prefix = `weaver-demo:${credential}:`
  try {
    for (const key of Object.keys(sessionStorage)) if (key.startsWith(prefix)) sessionStorage.removeItem(key)
    sessionStorage.removeItem(tokenKey)
  } catch { /* Memory fallback has no browser data to remove. */ }
  memory.clear()
  credential = ''
  generation++
  ended = true
  await create()
}
export function requestDemoReset() { window.dispatchEvent(new Event('weaver-reset-demo')) }

/** Local persistence stays unchanged; demo data belongs only to the current tab/session. */
export const workspaceStorage: Pick<Storage,'getItem'|'setItem'|'removeItem'> = {
  getItem(key) {
    if (!isDemo()) return localStorage.getItem(key)
    if (memoryOnly) return memory.get(key) ?? null
    try { return sessionStorage.getItem(`weaver-demo:${credential}:${key}`) } catch { memoryOnly=true;return memory.get(key) ?? null }
  },
  setItem(key,value) {
    if (!isDemo()) return localStorage.setItem(key,value)
    memory.set(key,value)
    if (!memoryOnly) try { sessionStorage.setItem(`weaver-demo:${credential}:${key}`,value) } catch { memoryOnly=true }
  },
  removeItem(key) {
    if (!isDemo()) return localStorage.removeItem(key)
    memory.delete(key)
    if (!memoryOnly) try { sessionStorage.removeItem(`weaver-demo:${credential}:${key}`) } catch { memoryOnly=true }
  },
}
export const draftLocation = () => isDemo() ? usesMemoryOnly() ? 'Draft kept in this page' : 'Draft saved for this demo session' : 'Draft saved on this device'
