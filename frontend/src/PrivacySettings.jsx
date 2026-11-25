import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'

import { api } from './api'

// #31: what other students can see. The name is deliberately not listed -
// friends need it to tell who is who.
export const PRIVACY_OPTIONS = [
  { name: 'show_email', label: 'Email address', short: 'email', description: 'Shown on your friend requests, friends list, profile and chats.' },
  { name: 'show_bio', label: 'Bio', short: 'bio', description: 'Shown on your friend profile and friends list.' },
  { name: 'show_profile_picture', label: 'Profile photo', short: 'photo', description: 'Others see your initial instead when this is off.' },
]

function joinList(items) {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

export function privacySummary(settings) {
  const hidden = PRIVACY_OPTIONS.filter((option) => !settings[option.name]).map((option) => option.short)
  if (hidden.length === 0) return 'Other students can see your name, email, bio and photo.'
  if (hidden.length === PRIVACY_OPTIONS.length) return 'Other students only see your name. Your email, bio and photo are hidden.'
  return `Hidden from other students: ${joinList(hidden)}. Your name is always visible.`
}

// With no name, a student who hides their email would be a blank "?" to their
// friends (and on friend requests), so nudge them to add one.
function NameNote() {
  return <p className="field__note" role="note">Add your name in <Link to="/profile">Edit profile</Link> so friends can recognise you while your email is hidden.</p>
}

export default function PrivacySettings() {
  const [saved, setSaved] = useState(null)
  const [hasName, setHasName] = useState(true)
  const [draft, setDraft] = useState(null)
  const [open, setOpen] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [saving, setSaving] = useState(false)
  const [justSaved, setJustSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoadError('')
    api('/profile/').then((data) => {
      if (!active) return
      const loaded = {
        show_email: data.user.show_email !== false,
        show_bio: data.user.show_bio !== false,
        show_profile_picture: data.user.show_profile_picture !== false,
      }
      setSaved(loaded)
      setDraft(loaded)
      setHasName(Boolean(`${data.user.first_name || ''}${data.user.last_name || ''}`.trim()))
    }).catch((err) => {
      if (active) setLoadError(err.status === 401 ? 'Your session expired. Please sign in again.' : 'We couldn’t load your privacy settings. Try again.')
    })
    return () => { active = false }
  }, [attempt])

  function toggle(event) {
    const { name, checked } = event.target
    setDraft((current) => ({ ...current, [name]: checked }))
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
      await api('/profile/privacy/', { method: 'PUT', body: draft })
      setSaved(draft)
      setOpen(false)
      setJustSaved(true)
    } catch (err) {
      setError(err.message || 'We couldn’t save your privacy settings. Try again.')
    } finally { setSaving(false) }
  }

  return <section className="panel account-option" aria-labelledby="privacy-heading">
    <div className="account-option__icon"><ShieldCheck size={23} /></div>
    <div className="account-option__body">
      <h2 id="privacy-heading">Privacy</h2>
      {loadError ? <>
        <p role="alert">{loadError}</p>
        <button className="button button--secondary" onClick={() => setAttempt((value) => value + 1)}>Try again</button>
      </> : !saved ? <p role="status">Loading your privacy settings…</p> : open ? <form onSubmit={submit} className="form-stack" aria-labelledby="privacy-heading">
        <p>Choose what other students can see. Your name is always visible so friends know who you are.</p>
        {error && <div className="form-alert" role="alert">{error}</div>}
        <div className="privacy-options">
          {PRIVACY_OPTIONS.map((option) => <label className="privacy-option" key={option.name}>
            <span className="privacy-option__copy">
              <strong>Show my {option.label.toLowerCase()}</strong>
              <small>{option.description}</small>
            </span>
            <input type="checkbox" role="switch" className="privacy-switch" name={option.name} checked={draft[option.name]} onChange={toggle} />
          </label>)}
        </div>
        {!draft.show_email && !hasName && <NameNote />}
        <div className="form-actions">
          <button type="button" className="button button--secondary" onClick={cancel} disabled={saving}>Cancel</button>
          <button type="submit" className="button button--primary" disabled={saving}>{saving ? 'Saving…' : 'Save privacy settings'}</button>
        </div>
      </form> : <>
        {justSaved && <div className="form-alert form-alert--success" role="status">Your privacy settings have been saved.</div>}
        <p>{privacySummary(saved)}</p>
        {!saved.show_email && !hasName && <NameNote />}
        <button className="button button--secondary" onClick={() => setOpen(true)}>Edit privacy</button>
      </>}
    </div>
  </section>
}
