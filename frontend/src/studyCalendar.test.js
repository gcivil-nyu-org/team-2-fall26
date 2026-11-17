import assert from 'node:assert/strict'
import test from 'node:test'

import { availableHours, calendarMidnight, dateLabel, nextAvailabilityBlock, shiftDate, weekDays } from './studyCalendar.js'

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

test('sessions split only at Eastern midnight', () => {
  const sessions = [
    { id: 2, starts_at: '2026-10-20T03:00:00Z', ends_at: '2026-10-20T05:30:00Z' },
    { id: 1, starts_at: '2026-10-19T09:00:00Z', ends_at: '2026-10-19T10:00:00Z' },
  ]
  const days = weekDays('2026-10-19', sessions)
  assert.deepEqual(days[0].entries.map((entry) => entry.id), [1, 2])
  assert.equal(days[0].entries[0].time, '5:00 AM – 6:00 AM')
  assert.equal(days[0].entries[1].time, '11:00 PM – midnight')
  assert.equal(days[1].entries[0].time, 'Continues – 1:30 AM')
})

test('sessions ending exactly at midnight do not appear on the next day', () => {
  const days = weekDays('2026-10-19', [{ id: 1, starts_at: '2026-10-19T23:00:00Z', ends_at: '2026-10-20T04:00:00Z' }])
  assert.equal(days[0].entries.length, 1)
  assert.equal(days[1].entries.length, 0)
})

test('fall daylight-saving change keeps an Albert evening class in one day', () => {
  assert.equal(calendarMidnight('2026-11-02') - calendarMidnight('2026-11-01'), 25 * 3_600_000)
  const days = weekDays('2026-11-02', [{ id: 'class-1', starts_at: '2026-11-04T23:00:00Z', ends_at: '2026-11-05T01:30:00Z' }])
  assert.equal(days[2].entries[0].time, '6:00 PM – 8:30 PM')
  assert.equal(days[3].entries.length, 0)
})

test('availability totals support multiple blocks and an empty week', () => {
  assert.equal(availableHours([]), 0)
  assert.equal(availableHours([{ start_time: '09:00', end_time: '10:30' }, { start_time: '14:00', end_time: '16:00' }]), 3.5)
})

test('a new availability block starts after the ones already on that day', () => {
  const block = (weekday, start_time, end_time) => ({ weekday, start_time, end_time })
  assert.deepEqual(nextAvailabilityBlock([], 1), block(1, '09:00', '10:00'))
  assert.deepEqual(nextAvailabilityBlock([block(1, '09:00', '10:00')], 1), block(1, '10:00', '11:00'))
  assert.deepEqual(nextAvailabilityBlock([block(1, '09:00', '13:30')], 1), block(1, '13:30', '14:30'))
  // Other days don't matter, and a gap between blocks is used when it fits.
  assert.deepEqual(nextAvailabilityBlock([block(2, '09:00', '10:00')], 1), block(1, '09:00', '10:00'))
  assert.deepEqual(nextAvailabilityBlock([block(1, '09:00', '10:00'), block(1, '11:00', '12:00')], 1), block(1, '10:00', '11:00'))
  // Late in the day it can end at midnight, then wraps to the early morning.
  assert.deepEqual(nextAvailabilityBlock([block(1, '09:00', '23:00')], 1), block(1, '23:00', '00:00'))
  assert.deepEqual(nextAvailabilityBlock([block(1, '09:00', '00:00')], 1), block(1, '00:00', '01:00'))
  // A gap that doesn't start on a quarter hour is found from the previous block's end.
  assert.deepEqual(nextAvailabilityBlock([block(1, '00:00', '10:05'), block(1, '11:05', '00:00')], 1), block(1, '10:05', '11:05'))
  assert.deepEqual(nextAvailabilityBlock([block(1, '00:00', '14:40'), block(1, '15:40', '00:00')], 1), block(1, '14:40', '15:40'))
  assert.deepEqual(nextAvailabilityBlock([block(1, '09:00', '09:20')], 1), block(1, '09:20', '10:20'))
  // A completely full day falls back to the old default for the server to flag.
  assert.deepEqual(nextAvailabilityBlock([block(1, '00:00', '12:00'), block(1, '12:00', '00:00')], 1), block(1, '09:00', '10:00'))
})
