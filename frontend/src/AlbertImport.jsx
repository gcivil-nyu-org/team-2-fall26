import { useState } from 'react'
import { api } from './api'

export function AlbertImport({ open, onImported }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [choices, setChoices] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function submit(event) {
    event.preventDefault()
    const form = event.currentTarget
    setBusy(true)
    setError('')
    setMessage('')
    const body = new FormData()
    body.append('calendar', file)
    if (preview) {
      body.append('confirm', 'yes')
      for (const [uid, choice] of Object.entries(choices)) body.append(`course:${uid}`, choice)
    }
    try {
      const result = await api('/study/albert-import/', { method: 'POST', body })
      if (preview) {
        form.reset()
        setFile(null)
        setPreview(null)
        setMessage(`Synced ${result.meetings} class meetings for ${result.term}.`)
        onImported()
      } else {
        setChoices(Object.fromEntries(result.classes.map(({ uid, selected }) => [uid, selected])))
        setPreview(result)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return <details className="study-notice albert-import" open={open || undefined}>
    <summary>Import class schedule from Albert</summary>
    <form onSubmit={submit}>
      <p>Download your Class Calendar (.ics) in Albert. Upload a fresh export whenever your schedule changes.</p>
      <label className="field">
        <span className="field__label">Albert calendar file</span>
        <input type="file" accept=".ics,text/calendar" required disabled={busy} onChange={(event) => {
          setFile(event.target.files[0] || null)
          setPreview(null)
          setError('')
          setMessage('')
        }} />
      </label>
      {preview && <>
        <p><strong>{preview.term}</strong> · Match each class to an existing course or add it as a new course.</p>
        {preview.replacing && <p>This replaces previously imported class meetings for {preview.term}. Your courses and study sessions stay in place.</p>}
        {preview.classes.map(({ uid, title }) => <label className="field" key={uid}>
          <span className="field__label">{title}</span>
          <select required disabled={busy} value={choices[uid]} onChange={(event) => setChoices({ ...choices, [uid]: event.target.value })}>
            <option value="">Choose a course</option>
            {preview.courses.map((course) => <option key={course.id} value={course.id}>{course.name}{course.code ? ` · ${course.code}` : ''}</option>)}
            <option value="new">Add as a new course</option>
          </select>
        </label>)}
      </>}
      <button className="button button--primary button--small" disabled={busy || !file}>{busy ? 'Working…' : preview ? 'Sync class schedule' : 'Review import'}</button>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
    </form>
  </details>
}
