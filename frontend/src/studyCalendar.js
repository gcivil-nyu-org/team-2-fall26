import { EASTERN_TIME as NYU_TIME } from './api.js'
const easternDate = new Intl.DateTimeFormat('en-CA', {
  timeZone: NYU_TIME, year: 'numeric', month: '2-digit', day: '2-digit',
})
const easternOffset = new Intl.DateTimeFormat('en-US', { timeZone: NYU_TIME, timeZoneName: 'longOffset' })

export function calendarDate(instant = new Date()) {
  const parts = Object.fromEntries(easternDate.formatToParts(instant).map(({ type, value }) => [type, value]))
  return `${parts.year}-${parts.month}-${parts.day}`
}

export function calendarMidnight(date) {
  // New York's clock changes occur after local midnight.
  const instant = new Date(`${date}T00:00:00Z`)
  const offset = easternOffset.formatToParts(instant).find(({ type }) => type === 'timeZoneName').value.slice(3)
  return Date.parse(`${date}T00:00:00${offset || 'Z'}`)
}
export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export function shiftDate(iso, days) {
  const date = new Date(`${iso}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

export function dateLabel(iso, options = {}) {
  return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', ...options })
    .format(new Date(`${iso}T00:00:00Z`))
}

export function timeLabel(iso) {
  return new Intl.DateTimeFormat('en-US', { timeZone: NYU_TIME, hour: 'numeric', minute: '2-digit' }).format(new Date(iso))
}

export function weekDays(start, sessions) {
  return WEEKDAYS.map((name, index) => {
    const date = shiftDate(start, index)
    const startMs = calendarMidnight(date)
    const endMs = calendarMidnight(shiftDate(date, 1))
    const entries = sessions.filter((session) => Date.parse(session.starts_at) < endMs && Date.parse(session.ends_at) > startMs)
      .map((session) => ({
        ...session,
        time: `${Date.parse(session.starts_at) < startMs ? 'Continues' : timeLabel(session.starts_at)} – ${Date.parse(session.ends_at) >= endMs ? 'midnight' : timeLabel(session.ends_at)}`,
      })).sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at) || a.id - b.id)
    return { name, date, entries }
  })
}

export function availableHours(blocks) {
  const minutes = (value) => {
    const [hours, mins] = value.split(':').map(Number)
    return hours * 60 + mins
  }
  return blocks.reduce((total, block) => {
    const start = minutes(block.start_time)
    const end = block.end_time === '00:00' && start > 0 ? 1440 : minutes(block.end_time)
    return total + Math.max(0, end - start) / 60
  }, 0)
}

const clockMinutes = (value) => {
  const [hours, mins] = value.split(':').map(Number)
  return hours * 60 + mins
}
const clockTime = (total) => `${String(Math.floor(total / 60) % 24).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`

// A one-hour block for a day that doesn't overlap the blocks already on it:
// the first free hour from 9:00 AM onward, then from midnight. Falls back to
// 9:00–10:00 when the day is full, which the server will flag.
export function nextAvailabilityBlock(blocks, weekday) {
  const taken = blocks.filter((block) => block.weekday === weekday).map((block) => {
    const start = clockMinutes(block.start_time)
    return [start, block.end_time === '00:00' && start > 0 ? 1440 : clockMinutes(block.end_time)]
  })
  const starts = []
  for (let start = 540; start <= 1380; start += 15) starts.push(start)
  for (let start = 0; start < 540; start += 15) starts.push(start)
  const start = starts.find((candidate) => taken.every(([from, to]) => candidate + 60 <= from || candidate >= to)) ?? 540
  return { weekday, start_time: clockTime(start), end_time: clockTime(start + 60) }
}
