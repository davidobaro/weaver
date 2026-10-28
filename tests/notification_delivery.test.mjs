import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from '../frontend/node_modules/typescript/lib/typescript.js'

const source = readFileSync(new URL('../frontend/src/notificationDelivery.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022}})
const { deliverReminders } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

function fixture() {
  const saved = new Map()
  const calls = [], shown = []
  const env = {
    active: () => true, permitted: () => true,
    storage: {getItem: key => saved.get(key), setItem: (key, value) => saved.set(key, value), removeItem: key => saved.delete(key)},
    request: async path => { calls.push(path); return path.includes('/claim') ? {count: 3, token: 'batch'} : {saved: true} },
    show: count => shown.push(count),
  }
  return {saved, calls, shown, env}
}
const deliver = env => deliverReminders(env, 'device', 'America/New_York')

test('off or ungranted permission never reserves or shows an alert', async () => {
  for (const flag of ['active', 'permitted']) {
    const {env, calls, shown} = fixture()
    env[flag] = () => false
    await deliver(env)
    assert.deepEqual(calls, []); assert.deepEqual(shown, [])
  }
})

test('groups reminders, acknowledges delivery, and clears pending receipt', async () => {
  const {env, calls, shown, saved} = fixture()
  await deliver(env)
  assert.deepEqual(shown, [3])
  assert.equal(calls.length, 2)
  assert.equal(calls[1], '/notifications/device/batch/ack')
  assert.equal(saved.size, 0)
})

test('opting out while the claim is in flight prevents showing it', async () => {
  const {env, shown} = fixture()
  env.request = async () => { env.active = () => false; return {count: 1, token: 'batch'} }
  await deliver(env)
  assert.deepEqual(shown, [])
})

test('unsupported notification constructor does not acknowledge delivery', async () => {
  const {env, calls, saved} = fixture()
  env.show = () => { throw new TypeError('Unsupported') }
  await assert.rejects(deliver(env), TypeError)
  assert.equal(calls.length, 1)
  assert.equal(saved.size, 0)
})

test('lost acknowledgment is persisted and retried before another claim', async () => {
  const {env, saved, calls, shown} = fixture()
  const request = env.request
  env.request = async path => { if (path.endsWith('/ack')) throw new Error('offline'); return request(path) }
  await assert.rejects(deliver(env), /offline/)
  assert.equal(saved.get('weaver-notification-ack'), 'batch')
  calls.length = 0
  env.request = async path => { calls.push(path); return path.includes('/claim') ? {token: null, count: 0} : {saved: true} }
  await deliver(env)
  assert.equal(calls[0], '/notifications/device/batch/ack')
  assert.equal(saved.size, 0)
  assert.deepEqual(shown, [3])
})
