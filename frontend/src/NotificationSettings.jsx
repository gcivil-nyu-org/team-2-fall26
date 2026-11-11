import { useEffect, useState } from 'react'
import { Bell } from 'lucide-react'

import { api } from './api'

// #37: the lead-time choices come from the server (GET /api/profile/notifications/).
export function leadTimeLabel(minutes) {
  if (minutes === 60) return '1 hour'
  if (minutes === 120) return '2 hours'
  return `${minutes} minutes`
}

export function notificationSummary(settings) {
  if (!settings.study_reminders_enabled) return 'Study session reminders are off. Nothing will appear on your dashboard before a session.'
  return `Your dashboard reminds you ${leadTimeLabel(settings.study_reminder_minutes)} before a study session starts.`
}

export default function NotificationSettings() {
  const [saved, setSaved] = useState(null)
  const [draft, setDraft] = useState(null)
  const [leadTimes, setLeadTimes] = useState([])
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
      setLeadTimes(data.options.study_reminder_minutes)
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
      setError(err.errors?.study_reminder_minutes?.[0] || err.message || 'We couldn’t save your notification settings. Try again.')
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
        <p>Choose which reminders you get and how early they show up. Reminders appear in SemesterPilot on your dashboard. SemesterPilot doesn’t send emails or phone notifications.</p>
        {error && <div className="form-alert" role="alert">{error}</div>}
        <div className="notification-options">
          <label className="notification-option">
            <span className="notification-option__copy">
              <strong>Study session reminders</strong>
              <small>Show a reminder on your dashboard shortly before a study session starts.</small>
            </span>
            <input type="checkbox" role="switch" className="notification-switch" name="study_reminders_enabled" checked={draft.study_reminders_enabled} onChange={(event) => change({ study_reminders_enabled: event.target.checked })} />
          </label>
          <label className="notification-option notification-option--select">
            <span className="notification-option__copy">
              <strong>Remind me</strong>
              <small>How long before a session starts.</small>
            </span>
            <select name="study_reminder_minutes" className="notification-select" value={draft.study_reminder_minutes} disabled={!draft.study_reminders_enabled} onChange={(event) => change({ study_reminder_minutes: Number(event.target.value) })}>
              {leadTimes.map((minutes) => <option key={minutes} value={minutes}>{leadTimeLabel(minutes)} before</option>)}
            </select>
          </label>
        </div>
        <div className="form-actions">
          <button type="button" className="button button--secondary" onClick={cancel} disabled={saving}>Cancel</button>
          <button type="submit" className="button button--primary" disabled={saving}>{saving ? 'Saving…' : 'Save notification settings'}</button>
        </div>
      </form> : <>
        {justSaved && <div className="form-alert form-alert--success" role="status">Your notification settings have been saved.</div>}
        <p>{notificationSummary(saved)}</p>
        <button className="button button--secondary" onClick={() => setOpen(true)}>Edit notifications</button>
      </>}
    </div>
  </section>
}
