export class ApiError extends Error {
  constructor(message: string, public noteId?: number) { super(message) }
}

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined })
  if (!response.ok) {
    const result = await response.json().catch(() => null)
    const detail = result?.detail
    throw new ApiError(typeof detail === 'string' ? detail : detail?.message || 'Something went wrong. Please try again.', detail?.note_id)
  }
  return response.status === 204 ? undefined as T : response.json()
}
