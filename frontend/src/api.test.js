import assert from 'node:assert/strict'
import test from 'node:test'

import { api, buildRequestInit, formatDate, toEasternInput } from './api.js'
import config from '../vite.config.js'

test('deadline prefill and display use Eastern time in different browser zones', () => {
  const originalZone = process.env.TZ
  try {
    for (const zone of ['America/New_York', 'Asia/Tokyo', 'UTC']) {
      process.env.TZ = zone
      for (const month of ['07', '11']) {
        const deadline = `2026-${month}-20T17:45:00+00:00`
        assert.equal(toEasternInput(deadline), `2026-${month}-20T${month === '07' ? '13' : '12'}:45`)
        assert.match(formatDate(deadline), month === '07' ? /1:45 PM EDT/ : /12:45 PM EST/)
      }
    }
  } finally {
    if (originalZone === undefined) delete process.env.TZ
    else process.env.TZ = originalZone
  }
})

test('deadline prefill converts explicit offsets without changing the instant', () => {
  assert.equal(toEasternInput('2026-11-20T12:45:00-05:00'), '2026-11-20T12:45')
  assert.equal(toEasternInput(null), '')
  assert.equal(formatDate(null), 'No deadline')
})

test('Vite serves the router base in development and the static asset base in production', () => {
  assert.equal(config({ command: 'serve' }).base, '/app/')
  assert.equal(config({ command: 'build' }).base, '/static/frontend/')
})

test('a JSON body is stringified and gets a JSON content type', () => {
  const built = buildRequestInit({ method: 'POST', body: { title: 'Midterm' } })
  assert.equal(built.headers['Content-Type'], 'application/json')
  assert.equal(built.body, JSON.stringify({ title: 'Midterm' }))
  assert.equal(built.needsCsrf, true)
})

test('a FormData body (file upload) is passed through untouched with no forced content type', () => {
  const body = new FormData()
  body.append('profile_picture', new Blob(['x'], { type: 'image/png' }), 'avatar.png')
  const built = buildRequestInit({ method: 'POST', body })
  assert.equal(built.headers['Content-Type'], undefined)
  assert.equal(built.body, body)
  assert.equal(built.needsCsrf, true)
})

test('a request with no body sets no content type and no body', () => {
  const built = buildRequestInit({ method: 'DELETE' })
  assert.equal(built.headers['Content-Type'], undefined)
  assert.equal(built.body, undefined)
  assert.equal(built.needsCsrf, true)
})

test('GET/HEAD/OPTIONS requests never need a CSRF token', () => {
  for (const method of ['GET', 'HEAD', 'OPTIONS']) {
    assert.equal(buildRequestInit({ method }).needsCsrf, false)
  }
})


test('reschedule warnings survive the API error response', async (t) => {
  const warnings = ['This time overlaps another study session.']
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, status: 409, json: async () => ({ detail: 'Review warnings.', warnings }) }))
  await assert.rejects(api('/study/sessions/7/'), (error) => {
    assert.equal(error.status, 409)
    assert.deepEqual(error.warnings, warnings)
    return true
  })
})
