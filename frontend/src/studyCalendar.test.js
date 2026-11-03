import assert from 'node:assert/strict'
import test from 'node:test'

import { availableHours, dateLabel, shiftDate, weekDays } from './studyCalendar.js'

test('week navigation crosses month/year boundaries without local timezone shifts', () => {
  assert.equal(shiftDate('2026-12-28', 7), '2027-01-04')
  assert.equal(shiftDate('2027-01-04', -7), '2026-12-28')
  assert.equal(dateLabel('2026-10-19'), 'Oct 19')
})

test('weekly calendar renders seven ordered days and an empty state per day', () => {
  const days = weekDays('2026-10-19', [])
  assert.equal(days.length, 7)
  assert.equal(days[0].name, 'Monday')
  assert.equal(days[6].date, '2026-10-25')
  assert.ok(days.every((day) => day.entries.length === 0))
})

test('sessions sort by time and split across midnight with UTC time labels', () => {
  const sessions = [
    { id: 2, starts_at: '2026-10-19T23:00:00Z', ends_at: '2026-10-20T01:30:00Z' },
    { id: 1, starts_at: '2026-10-19T09:00:00Z', ends_at: '2026-10-19T10:00:00Z' },
  ]
  const days = weekDays('2026-10-19', sessions)
  assert.deepEqual(days[0].entries.map((entry) => entry.id), [1, 2])
  assert.equal(days[0].entries[0].time, '9:00 AM – 10:00 AM')
  assert.equal(days[0].entries[1].time, '11:00 PM – midnight')
  assert.equal(days[1].entries[0].time, 'Continues – 1:30 AM')
})

test('sessions ending exactly at midnight do not appear on the next day', () => {
  const days = weekDays('2026-10-19', [{ id: 1, starts_at: '2026-10-19T23:00:00Z', ends_at: '2026-10-20T00:00:00Z' }])
  assert.equal(days[0].entries.length, 1)
  assert.equal(days[1].entries.length, 0)
})

test('availability totals support multiple blocks and an empty week', () => {
  assert.equal(availableHours([]), 0)
  assert.equal(availableHours([{ start_time: '09:00', end_time: '10:30' }, { start_time: '14:00', end_time: '16:00' }]), 3.5)
})
