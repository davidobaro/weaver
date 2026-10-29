import { expireSession, isDemo, sessionAuthorization, sessionGeneration, sessionIsEnded } from './demoSession'

export class ApiError extends Error {
  constructor(message: string, public noteId?: number) { super(message) }
}

async function request(path: string, method = 'GET', body?: unknown) {
  if (isDemo() && sessionIsEnded()) throw new ApiError('This temporary session has ended.')
  const generation = sessionGeneration()
  const response = await fetch(`/api${path}`, { method, headers: {...sessionAuthorization(), ...(body ? {'Content-Type':'application/json'} : {})}, body: body ? JSON.stringify(body) : undefined, cache:'no-store' })
  if (generation !== sessionGeneration()) throw new ApiError('The demo session changed. Please use the current workspace.')
  if (!response.ok) {
    if (response.status === 401 && isDemo()) expireSession(generation)
    const result = await response.json().catch(() => null)
    const detail = result?.detail
    throw new ApiError(typeof detail === 'string' ? detail : detail?.message || 'Something went wrong. Please try again.', detail?.note_id)
  }
  return {response,generation}
}

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const {response,generation} = await request(path,method,body)
  const value = response.status === 204 ? undefined : await response.json()
  if (generation !== sessionGeneration()) throw new ApiError('The demo session changed. Please use the current workspace.')
  return value as T
}

export async function exportWorkspace() {
  const {response,generation} = await request('/export')
  const blob = await response.blob()
  if (generation !== sessionGeneration()) return
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href=url; anchor.download='weaver-export.json';anchor.click()
  window.setTimeout(()=>URL.revokeObjectURL(url),1000)
}
