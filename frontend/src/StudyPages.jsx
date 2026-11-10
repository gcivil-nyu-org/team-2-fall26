import { useEffect, useState } from 'react'
import { NavLink, useSearchParams } from 'react-router-dom'
import { CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, Circle, Clock3, LockKeyhole, Plus, Sparkles, Trash2, UnlockKeyhole } from 'lucide-react'

import { api, formatDate, toEasternInput } from './api'
import { AlbertImport } from './AlbertImport'
import { availableHours, calendarDate, calendarMidnight, dateLabel, WEEKDAYS, weekDays } from './studyCalendar'

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
    <StudyHeader title="Your study hours" subtitle="Choose when you’re free each week in New York time.">
      <NavLink className="button button--secondary" to="/calendar"><CalendarDays size={17} /> View calendar</NavLink>
    </StudyHeader>
    {loading ? <p role="status">Loading your availability…</p> : loadError ? <LoadError message={loadError} retry={() => setAttempt((value) => value + 1)} /> : <>
      {!blocks.length && <div className="study-notice"><Clock3 size={20} /><div><strong>Start with your available time</strong><p>Set your weekly availability before a study schedule can be generated. Your time blocks are private to your account.</p></div></div>}
      {message && <div className="study-notice study-notice--success" role="status">{message}</div>}
      {error && <div className="study-notice study-notice--error" role="alert">{error}</div>}
      <form onSubmit={submit} className="panel availability-panel">
        <div className="panel__header"><div><p className="kicker">Repeats every week · Eastern time</p><h2>Weekly availability</h2></div><span className="count-pill">{Number.isFinite(hours) ? hours.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'} hours / week</span></div>
        <fieldset disabled={saving} className="availability-days">
          <legend className="sr-only">Available time blocks for each day, in Eastern time</legend>
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
        <div className="availability-footer"><p>Use separate blocks for breaks. An end time of 12:00 AM means midnight at the end of that day.</p><div className="form-actions"><button className="button button--secondary" type="button" disabled={!dirty || saving} onClick={() => change(saved)}>Discard changes</button><button className="button button--primary" disabled={!dirty || saving}>{saving ? 'Saving…' : 'Save availability'}</button></div></div>
      </form>
    </>}
  </>
}

// Study sessions prepare for an assignment or an exam; class meetings have neither.
export function sessionLabel(session) {
  return session.assignment?.title ?? (session.exam ? `${session.exam.title} prep` : null)
}

function SessionEditor({ session, onSaved, onCancel }) {
  const [values, setValues] = useState({ starts_at: toEasternInput(session.starts_at), ends_at: toEasternInput(session.ends_at) })
  const [warnings, setWarnings] = useState([])
  const [error, setError] = useState('')
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)

  function change(event) {
    setValues((current) => ({ ...current, [event.target.name]: event.target.value }))
    setWarnings([])
    setErrors({})
    setError('')
  }

  async function save(event) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setErrors({})
    try {
      await api(`/study/sessions/${session.id}/`, { method: 'PATCH', body: { ...values, confirm_warnings: warnings.length > 0 } })
      onSaved()
    } catch (err) {
      setWarnings(err.warnings || [])
      setErrors(err.errors || {})
      setError(err.message)
    } finally { setSaving(false) }
  }

  return <section className="panel session-editor" aria-labelledby="session-editor-title">
    <h2 id="session-editor-title">Reschedule {sessionLabel(session)}</h2>
    <p>All dates and times are in Eastern time. {session.is_locked && 'This session stays locked after you move it.'}</p>
    {error && <div className="study-notice study-notice--error" role="alert">{error}</div>}
    {warnings.length > 0 && <div className="study-notice" role="alert"><div><strong>Move this session anyway?</strong><ul>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul><p>Confirming changes only this session.</p></div></div>}
    <form onSubmit={save} className="form-stack">
      <fieldset className="session-editor__fields" disabled={saving}>
        <legend className="sr-only">New session times in Eastern time</legend>
        {['starts_at', 'ends_at'].map((field) => <label className="field" key={field}><span className="field__label">{field === 'starts_at' ? 'Start' : 'End'} (Eastern)</span><input type="datetime-local" name={field} value={values[field]} onChange={change} onInput={change} required aria-invalid={Boolean(errors[field])} aria-describedby={errors[field] ? `session-${field}-error` : undefined} />{errors[field] && <span id={`session-${field}-error`} className="field__error">{errors[field].join(' ')}</span>}</label>)}
      </fieldset>
      <div className="form-actions"><button type="button" className="button button--secondary" disabled={saving} onClick={onCancel}>Cancel</button><button className="button button--primary" disabled={saving}>{saving ? 'Saving…' : warnings.length ? 'Move anyway' : 'Save new time'}</button></div>
    </form>
  </section>
}

function hoursLabel(hours) {
  const value = hours.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return `${value} more hour${hours === 1 ? '' : 's'}`
}

function courseLabel(course) {
  return course.code || course.name
}

function PlanSummary({ plan }) {
  const count = plan.sessions.length
  const last = plan.sessions.reduce((latest, session) => (latest && latest.ends_at > session.ends_at ? latest : session), null)
  return <>
    <div className="study-notice study-notice--success" role="status">
      <Sparkles size={20} />
      <div>
        <strong>{count ? `Created ${count} study session${count === 1 ? '' : 's'}` : 'No new sessions were needed'}</strong>
        <p>{count ? `Your plan runs through ${formatDate(last.ends_at)}. Use the week arrows to see later weeks.` : 'Everything with a deadline and workload is already covered, or there was nothing to plan.'}</p>
      </div>
    </div>
    {plan.shortfalls.length > 0 && <div className="study-notice study-notice--warning" role="alert">
      <Clock3 size={20} />
      <div>
        <strong>Not enough free time for everything</strong>
        <ul>{plan.shortfalls.map((item) => <li key={item.id}>{item.title} ({courseLabel(item.course)}) needs {hoursLabel(item.hours_short)} before {formatDate(item.due_date)}</li>)}</ul>
        <p>Add more availability or adjust the estimate, then generate again. <NavLink to="/availability">Edit availability</NavLink></p>
      </div>
    </div>}
    {plan.skipped.length > 0 && <div className="study-notice">
      <CalendarDays size={20} />
      <div>
        <strong>Not included in this plan</strong>
        <ul>{plan.skipped.map((item) => <li key={item.id}>{item.title} ({courseLabel(item.course)}): {item.reason}</li>)}</ul>
      </div>
    </div>}
  </>
}

export function CalendarPage() {
  const [params, setParams] = useSearchParams()
  const week = params.get('week') || ''
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  const [editing, setEditing] = useState(null)
  const [busy, setBusy] = useState(null)
  const [actionError, setActionError] = useState('')
  const [message, setMessage] = useState('')
  const [confirmingPlan, setConfirmingPlan] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [plan, setPlan] = useState(null)

  async function generatePlan() {
    setGenerating(true)
    setActionError('')
    setMessage('')
    try {
      setPlan(await api('/study/generate/', { method: 'POST' }))
      setConfirmingPlan(false)
      setAttempt((value) => value + 1)
    } catch (err) { setActionError(err.message) }
    finally { setGenerating(false) }
  }

  async function updateSession(session, body, describe) {
    setBusy(session.id)
    setActionError('')
    setMessage('')
    try {
      const result = await api(`/study/sessions/${session.id}/`, { method: 'PATCH', body })
      setData((current) => ({ ...current, sessions: current.sessions.map((item) => item.id === result.id ? { ...item, ...result } : item) }))
      setMessage(describe(result))
    } catch (err) { setActionError(err.message) }
    finally { setBusy(null) }
  }

  function toggleLock(session) {
    return updateSession(session, { is_locked: !session.is_locked },
      (result) => result.is_locked ? 'Session locked. Schedule regeneration will preserve it.' : 'Session unlocked.')
  }

  function toggleComplete(session) {
    return updateSession(session, { is_complete: !session.is_complete },
      (result) => result.is_complete ? 'Session marked complete. Regenerating your plan will keep it.' : 'Session reopened.')
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    setEditing(null)
    api(`/study/calendar/${week ? `?week=${encodeURIComponent(week)}` : ''}`).then((result) => { if (active) setData(result) })
      .catch((err) => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [week, attempt])

  const classes = data?.classes || []
  const days = data ? weekDays(data.week_start, [...data.sessions, ...classes]) : []
  // Hours inside this week only, so a session crossing midnight Sunday isn't double counted.
  const hoursThisWeek = (sessions) => sessions.reduce((total, session) => {
    const start = Math.max(Date.parse(session.starts_at), calendarMidnight(data.week_start))
    const end = Math.min(Date.parse(session.ends_at), calendarMidnight(data.week_end))
    return total + (end - start) / 3_600_000
  }, 0)
  const totalHours = data ? hoursThisWeek(data.sessions) : 0
  const completedHours = data ? hoursThisWeek(data.sessions.filter((session) => session.is_complete)) : 0
  const hoursLabelOf = (value) => value.toLocaleString('en-US', { maximumFractionDigits: 2 })
  const today = calendarDate()

  return <>
    <StudyHeader title="Your study calendar" subtitle="Class meetings and study sessions, shown in Eastern time.">
      <NavLink className="button button--secondary" to="/availability"><Clock3 size={17} /> Set availability</NavLink>
      <button className="button button--primary" disabled={!data || generating || confirmingPlan} onClick={() => {
        setPlan(null)
        setMessage('')
        setActionError(data.availability_configured ? '' : 'Set your weekly availability before generating a study plan.')
        setConfirmingPlan(data.availability_configured)
      }}><Sparkles size={17} /> Generate study plan</button>
    </StudyHeader>
    {confirmingPlan && <div className="study-notice study-notice--confirm" role="group" aria-label="Confirm study plan">
      <Sparkles size={20} />
      <div>
        <strong>Generate a new study plan?</strong>
        <p>This replaces your unlocked upcoming study sessions, including ones you moved by hand. Locked sessions and past sessions stay as they are.</p>
      </div>
      <div className="study-notice__actions">
        <button className="button button--primary button--small" onClick={generatePlan} disabled={generating}>{generating ? 'Generating…' : 'Generate'}</button>
        <button className="button button--secondary button--small" onClick={() => setConfirmingPlan(false)} disabled={generating}>Cancel</button>
      </div>
    </div>}
    {plan && <PlanSummary plan={plan} />}
    <AlbertImport open={params.get('import') === 'albert'} onImported={() => setAttempt((value) => value + 1)} />
    {loading ? <p role="status">Loading your week…</p> : error ? <>
      <LoadError message={error} retry={() => setAttempt((value) => value + 1)} />
      <button className="button button--soft" onClick={() => setParams({})}>Return to this week</button>
    </> : data && <>
      {!data.availability_configured && <div className="study-notice"><Clock3 size={20} /><div><strong>Make room for your study plan</strong><p>Set your weekly availability before a study schedule can be generated. <NavLink to="/availability">Choose your available hours</NavLink></p></div></div>}
      {actionError && <div className="study-notice study-notice--error" role="alert">{actionError}</div>}
      {message && <div className="study-notice study-notice--success" role="status">{message}</div>}
      {editing && <SessionEditor key={editing.id} session={editing} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); setMessage('Session rescheduled.'); setAttempt((value) => value + 1) }} />}
      <section className="panel calendar-panel" aria-label="Weekly study calendar">
        <div className="panel__header calendar-toolbar">
          <div><p className="kicker">Monday – Sunday · Eastern time</p><h2 aria-live="polite">{dateLabel(data.week_start)} – {dateLabel(days[6].date, { year: 'numeric' })}</h2></div>
          <div className="calendar-navigation"><button className="icon-button" aria-label="Previous week" onClick={() => setParams({ week: data.previous_week })}><ChevronLeft size={20} /></button><button className="button button--secondary button--small" onClick={() => setParams({})}>This week</button><button className="icon-button" aria-label="Next week" onClick={() => setParams({ week: data.next_week })}><ChevronRight size={20} /></button></div>
        </div>
        <div className="calendar-summary"><span>{data.sessions.length} session{data.sessions.length === 1 ? '' : 's'}</span><span>{totalHours ? `${hoursLabelOf(completedHours)} of ${hoursLabelOf(totalHours)} study hours completed` : '0 study hours'}</span><span>Time zone: New York</span></div>
        {!data.sessions.length && !classes.length && <div className="calendar-empty" role="status"><CalendarDays size={26} /><div><h3>No events this week</h3><p>Browse another week or import your class schedule.</p></div></div>}
        <p className="calendar-scroll-hint">Scroll horizontally to see all seven days.</p>
        <div className="calendar-scroll" tabIndex="0" role="region" aria-label="Days of the week; scroll horizontally on smaller screens">
          <div className="calendar-week">
            {days.map((day) => <section key={day.date} className={`calendar-day ${day.date === today ? 'calendar-day--today' : ''}`} aria-label={`${day.name}, ${day.date}`}>
              <header className="calendar-day__header"><span>{day.name.slice(0, 3)}</span><time dateTime={day.date}>{new Date(`${day.date}T00:00:00Z`).getUTCDate()}</time>{day.date === today && <small>Today</small>}</header>
              <div className="calendar-day__sessions">
                {day.entries.length ? day.entries.map((session) => <article key={session.id} className={`calendar-session ${sessionLabel(session) ? `${session.is_locked ? 'calendar-session--locked' : ''} ${session.is_complete ? 'calendar-session--complete' : ''}` : 'calendar-session--class'}`}>
                  <div className="calendar-session__time"><Clock3 size={12} /><span>{session.time}</span></div>
                  {session.is_complete && <span className="calendar-session__complete"><CheckCircle2 size={12} /> Completed</span>}
                  {session.is_locked && <span className="calendar-session__locked"><LockKeyhole size={12} /> Locked</span>}
                  <h3>{sessionLabel(session) || 'Class meeting'}</h3>
                  <NavLink to={`/courses/${session.course.id}`}>{sessionLabel(session) ? session.course.code || session.course.name : session.course.name}</NavLink>
                  {sessionLabel(session) && session.course.code && <p>{session.course.name}</p>}
                  {session.location && <p>{session.location}</p>}
                  {sessionLabel(session) && <div className="calendar-session__actions"><button className="button button--ghost button--small" aria-label={session.is_complete ? `Reopen ${sessionLabel(session)}` : `Mark ${sessionLabel(session)} complete`} disabled={busy !== null || editing !== null} onClick={() => toggleComplete(session)}>{session.is_complete ? <Circle size={13} /> : <CheckCircle2 size={13} />}{session.is_complete ? 'Reopen' : 'Complete'}</button><button className="button button--ghost button--small" aria-label={`${session.is_locked ? 'Unlock' : 'Lock'} ${sessionLabel(session)}`} disabled={busy !== null || editing !== null} onClick={() => toggleLock(session)}>{session.is_locked ? <UnlockKeyhole size={13} /> : <LockKeyhole size={13} />}{session.is_locked ? 'Unlock' : 'Lock'}</button><button className="button button--ghost button--small" aria-label={`Reschedule ${sessionLabel(session)}`} disabled={busy !== null || editing !== null} onClick={() => { setEditing(session); setMessage(''); setActionError('') }}>Reschedule</button></div>}
                </article>) : <p className="calendar-day__empty">No sessions</p>}
              </div>
            </section>)}
          </div>
        </div>
      </section>
    </>}
  </>
}
