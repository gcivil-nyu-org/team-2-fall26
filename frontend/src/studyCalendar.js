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
