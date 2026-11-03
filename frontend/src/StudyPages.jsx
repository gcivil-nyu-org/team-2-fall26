import { useEffect, useState } from 'react'
import { NavLink, useSearchParams } from 'react-router-dom'
import { CalendarDays, ChevronLeft, ChevronRight, Clock3, Plus, Trash2 } from 'lucide-react'

import { api } from './api'
import { availableHours, dateLabel, WEEKDAYS, weekDays } from './studyCalendar'

function StudyHeader({ title, subtitle, children }) {
  return <header className="page-header">
    <div><p className="kicker">Study planning</p><h1>{title}</h1><p className="page-header__subtitle">{subtitle}</p></div>
    <div className="page-header__actions">{children}</div>
  </header>
}

function LoadError({ message, retry }) {
  return <div className="study-notice study-notice--error" role="alert"><p>{message}</p><button className="button button--secondary" onClick={retry}>Try again</button></div>
}

export function AvailabilityPage() {
  const [blocks, setBlocks] = useState([])
  const [saved, setSaved] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    api('/study/availability/').then((data) => {
      if (active) { setBlocks(data.blocks); setSaved(data.blocks) }
    }).catch((err) => { if (active) setLoadError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [attempt])

  const dirty = JSON.stringify(blocks) !== JSON.stringify(saved)
  const hours = availableHours(blocks)

  function change(next) {
    setBlocks(next)
    setErrors({})
    setError('')
    setMessage('')
  }

  function add(weekday) {
    change([...blocks, { weekday, start_time: '09:00', end_time: '10:00' }])
  }

  function update(index, field, value) {
    change(blocks.map((block, i) => i === index ? { ...block, [field]: value } : block))
  }

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const data = await api('/study/availability/', { method: 'PUT', body: { blocks } })
      setBlocks(data.blocks)
      setSaved(data.blocks)
      setErrors({})
      setMessage(data.configured ? 'Weekly availability saved. Future study plans will use these time blocks.' : 'Availability cleared. Set available time before generating a study plan.')
    } catch (err) {
      setErrors(err.errors || {})
      setError(err.message)
    } finally { setSaving(false) }
  }

  return <>
    <StudyHeader title="Your study hours" subtitle="Choose when you’re free each week. All times are in UTC.">
      <NavLink className="button button--secondary" to="/calendar"><CalendarDays size={17} /> View calendar</NavLink>
    </StudyHeader>
    {loading ? <p role="status">Loading your availability…</p> : loadError ? <LoadError message={loadError} retry={() => setAttempt((value) => value + 1)} /> : <>
      {!blocks.length && <div className="study-notice"><Clock3 size={20} /><div><strong>Start with your available time</strong><p>Set your weekly availability before a study schedule can be generated. Your time blocks are private to your account.</p></div></div>}
      {message && <div className="study-notice study-notice--success" role="status">{message}</div>}
      {error && <div className="study-notice study-notice--error" role="alert">{error}</div>}
      <form onSubmit={submit} className="panel availability-panel">
        <div className="panel__header"><div><p className="kicker">Repeats every week · UTC</p><h2>Weekly availability</h2></div><span className="count-pill">{Number.isFinite(hours) ? hours.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'} hours / week</span></div>
        <fieldset disabled={saving} className="availability-days">
          <legend className="sr-only">Available time blocks for each day, in UTC</legend>
          {WEEKDAYS.map((day, weekday) => {
            const daily = blocks.map((block, index) => ({ ...block, index })).filter((block) => block.weekday === weekday)
            return <section className="availability-day" aria-labelledby={`day-${weekday}`} key={day}>
              <div className="availability-day__label"><h3 id={`day-${weekday}`}>{day}</h3><span>{daily.length ? `${daily.length} block${daily.length === 1 ? '' : 's'}` : 'Not available'}</span></div>
              <div className="availability-day__blocks">
                {daily.map((block, position) => {
                  const fieldErrors = errors[block.index] || {}
                  const id = `block-${block.index}`
                  return <div key={block.index} className="availability-block">
                    <div className="availability-block__inputs">
                      <label className={`field ${fieldErrors.start_time ? 'field--error' : ''}`}><span className="sr-only">{day} block {position + 1} start time</span><input type="time" step="60" required aria-invalid={Boolean(fieldErrors.start_time)} aria-describedby={fieldErrors.start_time ? `${id}-error` : undefined} value={block.start_time} onChange={(event) => update(block.index, 'start_time', event.target.value)} onInput={(event) => update(block.index, 'start_time', event.target.value)} /></label>
                      <span className="availability-block__separator">to</span>
                      <label className={`field ${fieldErrors.end_time ? 'field--error' : ''}`}><span className="sr-only">{day} block {position + 1} end time</span><input type="time" step="60" required aria-invalid={Boolean(fieldErrors.end_time)} aria-describedby={fieldErrors.end_time ? `${id}-error` : undefined} value={block.end_time} onChange={(event) => update(block.index, 'end_time', event.target.value)} onInput={(event) => update(block.index, 'end_time', event.target.value)} /></label>
                      <button className="icon-button" type="button" aria-label={`Remove ${day} block ${position + 1}`} onClick={() => change(blocks.filter((_, index) => index !== block.index))}><Trash2 size={16} /></button>
                    </div>
                    {Object.keys(fieldErrors).length > 0 && <span id={`${id}-error`} className="field__error">{Object.values(fieldErrors).flat().join(' ')}</span>}
                  </div>
                })}
                <button className="button button--ghost button--small availability-add" type="button" onClick={() => add(weekday)} aria-label={`Add time on ${day}`}><Plus size={15} /> Add time</button>
              </div>
            </section>
          })}
        </fieldset>
        <div className="availability-footer"><p>Use separate blocks for breaks. Blocks must end on the same day.</p><div className="form-actions"><button className="button button--secondary" type="button" disabled={!dirty || saving} onClick={() => change(saved)}>Discard changes</button><button className="button button--primary" disabled={!dirty || saving}>{saving ? 'Saving…' : 'Save availability'}</button></div></div>
      </form>
    </>}
  </>
}

export function CalendarPage() {
  const [params, setParams] = useSearchParams()
  const week = params.get('week') || ''
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    api(`/study/calendar/${week ? `?week=${encodeURIComponent(week)}` : ''}`).then((result) => { if (active) setData(result) })
      .catch((err) => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [week, attempt])

  const days = data ? weekDays(data.week_start, data.sessions) : []
  const totalHours = data ? data.sessions.reduce((total, session) => {
    const start = Math.max(Date.parse(session.starts_at), Date.parse(`${data.week_start}T00:00:00Z`))
    const end = Math.min(Date.parse(session.ends_at), Date.parse(`${data.week_end}T00:00:00Z`))
    return total + (end - start) / 3_600_000
  }, 0) : 0
  const today = new Date().toISOString().slice(0, 10)

  return <>
    <StudyHeader title="Your study calendar" subtitle="A little structure for the work ahead. All session times are in UTC.">
      <NavLink className="button button--secondary" to="/availability"><Clock3 size={17} /> Set availability</NavLink>
    </StudyHeader>
    {loading ? <p role="status">Loading your week…</p> : error ? <>
      <LoadError message={error} retry={() => setAttempt((value) => value + 1)} />
      <button className="button button--soft" onClick={() => setParams({})}>Return to this week</button>
    </> : data && <>
      {!data.availability_configured && <div className="study-notice"><Clock3 size={20} /><div><strong>Make room for your study plan</strong><p>Set your weekly availability before a study schedule can be generated. <NavLink to="/availability">Choose your available hours</NavLink></p></div></div>}
      <section className="panel calendar-panel" aria-label="Weekly study calendar">
        <div className="panel__header calendar-toolbar">
          <div><p className="kicker">Monday – Sunday · UTC</p><h2 aria-live="polite">{dateLabel(data.week_start)} – {dateLabel(days[6].date, { year: 'numeric' })}</h2></div>
          <div className="calendar-navigation"><button className="icon-button" aria-label="Previous week" onClick={() => setParams({ week: data.previous_week })}><ChevronLeft size={20} /></button><button className="button button--secondary button--small" onClick={() => setParams({})}>This week</button><button className="icon-button" aria-label="Next week" onClick={() => setParams({ week: data.next_week })}><ChevronRight size={20} /></button></div>
        </div>
        <div className="calendar-summary"><span>{data.sessions.length} session{data.sessions.length === 1 ? '' : 's'}</span><span>{totalHours.toLocaleString('en-US', { maximumFractionDigits: 2 })} study hours</span><span>Time zone: UTC</span></div>
        {!data.sessions.length && <div className="calendar-empty" role="status"><CalendarDays size={26} /><div><h3>No study sessions this week</h3><p>Your week is clear. Browse another week to see other scheduled sessions.</p></div></div>}
        <p className="calendar-scroll-hint">Scroll horizontally to see all seven days.</p>
        <div className="calendar-scroll" tabIndex="0" role="region" aria-label="Days of the week; scroll horizontally on smaller screens">
          <div className="calendar-week">
            {days.map((day) => <section key={day.date} className={`calendar-day ${day.date === today ? 'calendar-day--today' : ''}`} aria-label={`${day.name}, ${day.date}`}>
              <header className="calendar-day__header"><span>{day.name.slice(0, 3)}</span><time dateTime={day.date}>{new Date(`${day.date}T00:00:00Z`).getUTCDate()}</time>{day.date === today && <small>Today</small>}</header>
              <div className="calendar-day__sessions">
                {day.entries.length ? day.entries.map((session) => <article key={session.id} className="calendar-session">
                  <div className="calendar-session__time"><Clock3 size={12} /><span>{session.time}</span></div>
                  <h3>{session.assignment.title}</h3>
                  <NavLink to={`/courses/${session.course.id}`}>{session.course.code || session.course.name}</NavLink>
                  {session.course.code && <p>{session.course.name}</p>}
                </article>) : <p className="calendar-day__empty">No sessions</p>}
              </div>
            </section>)}
          </div>
        </div>
      </section>
    </>}
  </>
}
