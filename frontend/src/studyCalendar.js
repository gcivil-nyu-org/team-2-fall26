// Study planning uses UTC consistently for recurring availability and sessions.
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
  return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', hour: 'numeric', minute: '2-digit' }).format(new Date(iso))
}

export function weekDays(start, sessions) {
  return WEEKDAYS.map((name, index) => {
    const date = shiftDate(start, index)
    const startMs = Date.parse(`${date}T00:00:00Z`)
    const endMs = startMs + 86_400_000
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
  return blocks.reduce((total, block) => total + Math.max(0, minutes(block.end_time) - minutes(block.start_time)) / 60, 0)
}
