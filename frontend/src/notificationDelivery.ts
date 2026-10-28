type Environment = {
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
  active: () => boolean
  permitted: () => boolean
  request: <T>(path: string, method: 'POST') => Promise<T>
  show: (count: number) => void
}
const pendingKey = 'weaver-notification-ack'

/** Permission is checked both before reserving and before showing an alert. */
export async function deliverReminders(env: Environment, device: string, timezone: string) {
  if (!env.active() || !env.permitted()) return
  const endpoint = `/notifications/${device}`
  const pending = env.storage.getItem(pendingKey)
  if (pending) {
    await env.request(`${endpoint}/${pending}/ack`, 'POST')
    env.storage.removeItem(pendingKey)
  }
  const claim = await env.request<{token: string | null; count: number}>(`${endpoint}/claim?timezone=${encodeURIComponent(timezone)}`, 'POST')
  if (!env.active() || !env.permitted() || !claim.token) return
  env.show(claim.count)
  // Keep the receipt until acknowledged, including across reload/network failures.
  env.storage.setItem(pendingKey, claim.token)
  await env.request(`${endpoint}/${claim.token}/ack`, 'POST')
  env.storage.removeItem(pendingKey)
}
