import { useEffect, useState } from 'react'
import { Bell } from 'lucide-react'

import { api } from './api'

// #37: the lead-time choices come from the server (GET /api/profile/notifications/).
export function leadTimeLabel(minutes) {
  if (minutes === 60) return '1 hour'
  if (minutes === 120) return '2 hours'
  if (minutes > 120 && minutes % 60 === 0) return `${minutes / 60} hours`
  return `${minutes} minutes`
}

export function deadlineLeadLabel(hours) {
  return hours === 1 ? '1 hour' : `${hours} hours`
}

// One line per kind of alert, so the collapsed view shows exactly what is on.
export function notificationSummary(settings) {
  return [
    settings.study_reminders_enabled
      ? `Study sessions: reminded ${leadTimeLabel(settings.study_reminder_minutes)} before they start`
      : 'Study sessions: off',
    settings.deadline_reminders_enabled
      ? `Assignments and exams: reminded ${deadlineLeadLabel(settings.deadline_reminder_hours)} before they’re due`
      : 'Assignments and exams: off',
    settings.friend_request_alerts_enabled ? 'Friend requests: on' : 'Friend requests: off',
    settings.message_alerts_enabled ? 'New messages: on' : 'New messages: off',
  ]
}

function Switch({ name, title, hint, draft, change }) {
  return <label className="notification-option">
    <span className="notification-option__copy">
      <strong>{title}</strong>
      <small>{hint}</small>
    </span>
    <input type="checkbox" role="switch" className="notification-switch" name={name} checked={draft[name]} onChange={(event) => change({ [name]: event.target.checked })} />
  </label>
}

export default function NotificationSettings() {
  const [saved, setSaved] = useState(null)
  const [draft, setDraft] = useState(null)
  const [options, setOptions] = useState({ study_reminder_minutes: [], deadline_reminder_hours: [] })
  const [open, setOpen] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [saving, setSaving] = useState(false)
  const [justSaved, setJustSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoadError('')
    api('/profile/notifications/').then((data) => {
      if (!active) return
      setSaved(data.notifications)
      setDraft(data.notifications)
      setOptions(data.options)
    }).catch((err) => {
      if (active) setLoadError(err.status === 401 ? 'Your session expired. Please sign in again.' : 'We couldn’t load your notification settings. Try again.')
    })
    return () => { active = false }
  }, [attempt])

  function change(patch) {
    setDraft((current) => ({ ...current, ...patch }))
    setJustSaved(false)
    setError('')
  }

  function cancel() {
    setDraft(saved)
    setOpen(false)
    setJustSaved(false)
    setError('')
  }

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    setJustSaved(false)
    setError('')
    try {
      const data = await api('/profile/notifications/', { method: 'PUT', body: draft })
      setSaved(data.notifications)
      setDraft(data.notifications)
      setOpen(false)
      setJustSaved(true)
    } catch (err) {
      setError(Object.values(err.errors || {})[0]?.[0] || err.message || 'We couldn’t save your notification settings. Try again.')
    } finally { setSaving(false) }
  }

  return <section className="panel account-option" aria-labelledby="notifications-heading">
    <div className="account-option__icon"><Bell size={23} /></div>
    <div className="notification-settings">
      <h2 id="notifications-heading">Notifications</h2>
      {loadError ? <>
        <p role="alert">{loadError}</p>
        <button className="button button--secondary" onClick={() => setAttempt((value) => value + 1)}>Try again</button>
      </> : !saved ? <p role="status">Loading your notification settings…</p> : open ? <form onSubmit={submit} className="form-stack" aria-labelledby="notifications-heading">
        <p>Choose which reminders and alerts you get, and how early reminders show up. Everything appears inside SemesterPilot, on your dashboard and in the sidebar. SemesterPilot doesn’t send emails or phone notifications.</p>
        {error && <div className="form-alert" role="alert">{error}</div>}
        <div className="notification-options">
          <Switch name="study_reminders_enabled" title="Study session reminders" hint="Show a reminder on your dashboard shortly before a study session starts." draft={draft} change={change} />
          <label className="notification-option notification-option--select">
            <span className="notification-option__copy">
              <strong>Study reminder timing</strong>
              <small>How long before a session starts.</small>
            </span>
            <select name="study_reminder_minutes" className="notification-select" value={draft.study_reminder_minutes} disabled={!draft.study_reminders_enabled} onChange={(event) => change({ study_reminder_minutes: Number(event.target.value) })}>
              {options.study_reminder_minutes.map((minutes) => <option key={minutes} value={minutes}>{leadTimeLabel(minutes)} before</option>)}
            </select>
          </label>
          <Switch name="deadline_reminders_enabled" title="Assignment and exam reminders" hint="Show a reminder on your dashboard when something is due soon." draft={draft} change={change} />
          <label className="notification-option notification-option--select">
            <span className="notification-option__copy">
              <strong>Due-date reminder timing</strong>
              <small>How long before an assignment is due or an exam starts.</small>
            </span>
            <select name="deadline_reminder_hours" className="notification-select" value={draft.deadline_reminder_hours} disabled={!draft.deadline_reminders_enabled} onChange={(event) => change({ deadline_reminder_hours: Number(event.target.value) })}>
              {options.deadline_reminder_hours.map((hours) => <option key={hours} value={hours}>{deadlineLeadLabel(hours)} before</option>)}
            </select>
          </label>
          <Switch name="friend_request_alerts_enabled" title="Friend request alerts" hint="Show a count on Friends in the sidebar when someone sends you a request or accepts yours." draft={draft} change={change} />
          <Switch name="message_alerts_enabled" title="New message alerts" hint="Show a count on Messages in the sidebar, and next to each friend who has written to you." draft={draft} change={change} />
        </div>
        <div className="form-actions">
          <button type="button" className="button button--secondary" onClick={cancel} disabled={saving}>Cancel</button>
          <button type="submit" className="button button--primary" disabled={saving}>{saving ? 'Saving…' : 'Save notification settings'}</button>
        </div>
      </form> : <>
        {justSaved && <div className="form-alert form-alert--success" role="status">Your notification settings have been saved.</div>}
        <ul className="notification-summary">{notificationSummary(saved).map((line) => <li key={line}>{line}</li>)}</ul>
        <button className="button button--secondary" onClick={() => setOpen(true)}>Edit notifications</button>
      </>}
    </div>
  </section>
}
