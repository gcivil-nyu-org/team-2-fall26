import assert from 'node:assert/strict'
import test from 'node:test'

import { formatDate, toUTCInput } from './api.js'
import config from '../vite.config.js'

test('deadline prefill and display stay in UTC in different browser zones', () => {
  const originalZone = process.env.TZ
  try {
    for (const zone of ['America/New_York', 'Asia/Tokyo', 'UTC']) {
      process.env.TZ = zone
      for (const month of ['07', '11']) {
        const deadline = `2026-${month}-20T17:45:00+00:00`
        assert.equal(toUTCInput(deadline), `2026-${month}-20T17:45`)
        assert.match(formatDate(deadline), /5:45 PM UTC/)
        // The offset-free form value is interpreted as UTC by Django.
        assert.equal(new Date(`${toUTCInput(deadline)}Z`).getTime(), Date.parse(deadline))
      }
    }
  } finally {
    if (originalZone === undefined) delete process.env.TZ
    else process.env.TZ = originalZone
  }
})

test('deadline prefill converts explicit offsets without changing the instant', () => {
  assert.equal(toUTCInput('2026-11-20T12:45:00-05:00'), '2026-11-20T17:45')
  assert.equal(toUTCInput(null), '')
  assert.equal(formatDate(null), 'No deadline')
})

test('Vite serves the router base in development and the static asset base in production', () => {
  assert.equal(config({ command: 'serve' }).base, '/app/')
  assert.equal(config({ command: 'build' }).base, '/static/frontend/')
})
