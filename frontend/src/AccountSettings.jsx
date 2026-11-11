import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, PauseCircle, Trash2 } from 'lucide-react'

import { api } from './api'

export default function AccountSettings({ onAccountClosed }) {
  const navigate = useNavigate()
  const [action, setAction] = useState(null)
  const [values, setValues] = useState({ current_password: '', confirmation: '' })
  const [errors, setErrors] = useState({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const deleting = action === 'delete'
  const word = deleting ? 'DELETE' : 'DEACTIVATE'

  function selectAction(next) {
    setAction(next)
    setValues({ current_password: '', confirmation: '' })
    setErrors({})
    setError('')
  }

  function update(event) {
    const { name, value } = event.target
    setValues((current) => ({ ...current, [name]: value }))
    setErrors((current) => ({ ...current, [name]: undefined }))
    setError('')
  }

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    setErrors({})
    setError('')
    try {
      await api(deleting ? '/account/' : '/account/deactivate/', {
        method: deleting ? 'DELETE' : 'POST', body: values,
      })
      onAccountClosed(action)
      navigate('/login', { replace: true, state: { accountAction: action } })
    } catch (err) {
      setErrors(err.errors || {})
      setError(err.status === 401 ? 'Your session has expired. Sign in again before changing your account.' : Object.keys(err.errors || {}).length ? 'Check the fields below. Your account has not been changed.' : err.message)
    } finally { setSaving(false) }
  }

  return <div className="account-settings">
    <header className="page-header"><div><p className="kicker">Your account</p><h1>Account settings</h1><p className="page-header__subtitle">Choose what happens to your account and its data.</p></div></header>
    <section className="panel account-option" aria-labelledby="deactivate-heading">
      <div className="account-option__icon"><PauseCircle size={23} /></div>
      <div><h2 id="deactivate-heading">Take a break</h2><p>Deactivating signs you out and disables access to your account. Your courses, assignments, and exams stay saved.</p><p>You’ll need an administrator to reactivate your account before you can sign in again.</p><button className="button button--secondary" disabled={saving} aria-expanded={action === 'deactivate'} aria-controls="account-confirmation" onClick={() => selectAction('deactivate')}>Deactivate account</button></div>
    </section>
    <section className="panel account-option account-option--danger" aria-labelledby="delete-heading">
      <div className="account-option__icon"><Trash2 size={23} /></div>
      <div><h2 id="delete-heading">Permanently delete your account</h2><p>This deletes your account and all of its courses, assignments, and exams. You will be signed out, and this action cannot be undone.</p><button className="button button--danger-outline" disabled={saving} aria-expanded={deleting} aria-controls="account-confirmation" onClick={() => selectAction('delete')}>Delete account</button></div>
    </section>
    {action && <section id="account-confirmation" className="panel account-confirmation" aria-labelledby="confirmation-heading">
      <div className="account-confirmation__heading"><AlertTriangle size={21} /><div><h2 id="confirmation-heading">{deleting ? 'Confirm permanent deletion' : 'Confirm deactivation'}</h2><p>{deleting ? 'Your account and its coursework will be permanently removed.' : 'Your data will stay saved, but you won’t be able to sign in until an administrator reactivates your account.'}</p></div></div>
      {error && <div className="form-alert" role="alert">{error}{error.includes('session has expired') && <> <a href="/app/login">Go to sign in</a></>}</div>}
      <form onSubmit={submit} className="form-stack">
        <fieldset disabled={saving} className="account-confirmation__fields">
          <legend className="account-sr-only">Confirm your account action</legend>
          <label className={`field ${errors.current_password ? 'field--error' : ''}`}><span className="field__label">Current password</span><input name="current_password" type="password" autoComplete="current-password" value={values.current_password} onChange={update} required autoFocus aria-invalid={Boolean(errors.current_password)} aria-describedby={errors.current_password ? 'account-password-error' : undefined} />{errors.current_password && <span id="account-password-error" className="field__error">{errors.current_password[0]}</span>}</label>
          <label className={`field ${errors.confirmation ? 'field--error' : ''}`}><span className="field__label">Type {word} to confirm</span><input name="confirmation" autoComplete="off" spellCheck={false} value={values.confirmation} onChange={update} required aria-invalid={Boolean(errors.confirmation)} aria-describedby={errors.confirmation ? 'account-word-error' : undefined} />{errors.confirmation && <span id="account-word-error" className="field__error">{errors.confirmation[0]}</span>}</label>
        </fieldset>
        <div className="form-actions"><button className="button button--secondary" type="button" disabled={saving} onClick={() => selectAction(null)}>Cancel</button><button className={`button ${deleting ? 'button--danger' : 'button--primary'}`} disabled={saving}>{saving ? 'Working…' : deleting ? 'Permanently delete account' : 'Confirm deactivation'}</button></div>
      </form>
    </section>}
  </div>
}
