import { useEffect, useState } from 'react'
import { NavLink, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ExternalLink, MapPin } from 'lucide-react'
import { api, formatDate } from './api'

function SaveEventButton({ event }) {
  const [saved, setSaved] = useState(event.is_saved)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function toggle() {
    setBusy(true); setError('')
    try { const result = await api(`/events/${event.id}/save/`, { method: saved ? 'DELETE' : 'PUT' }); setSaved(result.saved) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  return <div><button className="button button--secondary" disabled={busy || (!saved && (event.status !== 'confirmed' || Date.parse(event.starts_at) <= Date.now()))} aria-pressed={Boolean(saved)} onClick={toggle}>{saved ? 'Remove from calendar' : 'Save to calendar'}</button>{error && <p role="alert">{error}</p>}</div>
}

function LoadError({ error, retry }) {
  return <div className="study-notice study-notice--error" role="alert"><p>{error}</p><button className="button button--secondary" onClick={retry}>Try again</button></div>
}

export function EventsPage() {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const query = params.toString()
  useEffect(() => {
    const refresh = () => setAttempt((value) => value + 1)
    const timer = window.setInterval(refresh, 60_000)
    window.addEventListener('focus', refresh)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', refresh)
    }
  }, [])
  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    api(`/events/?${query}`).then((result) => { if (active) setData(result) })
      .catch((err) => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [query, attempt])

  function filter(event) {
    event.preventDefault()
    const values = new FormData(event.currentTarget)
    setParams(new URLSearchParams([...values.entries()].filter(([, value]) => value)))
  }
  function page(number) {
    const next = new URLSearchParams(params)
    next.set('page', number)
    setParams(next)
  }

  return <>
    <header className="page-header"><div><p className="kicker">Around NYU</p><h1>Discover events</h1><p className="page-header__subtitle">Find something worth making time for.</p></div></header>
    <form className="event-filters panel" onSubmit={filter} key={query} aria-label="Filter events">
      <label className="field"><span className="field__label">Search events</span><input name="q" defaultValue={params.get('q') || ''} maxLength={200} placeholder="Title, host, or location" /></label>
      <label className="field"><span className="field__label">From date</span><input name="date_from" type="date" defaultValue={params.get('date_from') || ''} /></label>
      <label className="field"><span className="field__label">Through date</span><input name="date_to" type="date" defaultValue={params.get('date_to') || ''} /></label>
      <label className="field"><span className="field__label">Category</span><select name="category" defaultValue={params.get('category') || ''}><option value="">All categories</option>{[...new Set([...(data?.categories || []), ...(params.get('category') ? [params.get('category')] : [])])].map((category) => <option key={category}>{category}</option>)}</select></label>
      <label className="event-career"><input type="checkbox" name="career" value="true" defaultChecked={params.get('career') === 'true'} /> Career development</label>
      <button className="button button--primary">Apply filters</button>
      <button className="button button--secondary" type="button" onClick={() => setParams({})}>Clear filters</button>
    </form>
    {loading && <p role="status">Loading events…</p>}
    {error && <LoadError error={error} retry={() => setAttempt((value) => value + 1)} />}
    {!loading && !error && data && <>
      <p className="event-feed-note">{data.last_synced_at ? `Last refreshed ${formatDate(data.last_synced_at, true)}. ` : 'Events have not been imported yet. '}{data.stale && data.last_synced_at && 'This list may be out of date. '}The public feed covers a limited date range; check Engage for more events.</p>
      {params.get('career') === 'true' && <p className="event-feed-note">Showing events tagged Professional &amp; Career Development on Engage. Other career events may appear under different categories.</p>}
      <p role="status">{data.count} {data.count === 1 ? 'event' : 'events'} found</p>
      <p className="event-feed-note">Only events that haven’t started yet are shown, soonest first.</p>
      {!data.events.length && <div className="empty-state panel"><h3>No upcoming events found</h3><p>Try different filters or check NYU Engage.</p></div>}
      <section className="event-grid" aria-label="NYU events">{data.events.map((event) => <article className="panel event-card" key={event.id}>
        <p className="kicker">{formatDate(event.starts_at, true)}</p>
        <h2><NavLink to={`/events/${event.id}`}>{event.title}</NavLink></h2>
        <p>Ends {formatDate(event.ends_at, true)}</p>
        <SaveEventButton key={`${event.id}-${event.is_saved}`} event={event} />
        <p>{event.host || 'NYU Engage'}</p>
        <p className="event-location"><MapPin size={15} aria-hidden="true" />{event.location || 'See Engage for location'}</p>
        <p className="event-categories">{event.categories.join(' · ')}</p>
        <NavLink className="text-link" to={`/events/${event.id}`}>View event</NavLink>
      </article>)}</section>
      {data.pages > 1 && <nav className="event-pagination" aria-label="Events pages"><button className="button button--secondary" disabled={data.page <= 1} onClick={() => page(data.page - 1)}>Previous</button><span>Page {data.page} of {data.pages}</span><button className="button button--secondary" disabled={data.page >= data.pages} onClick={() => page(data.page + 1)}>Next</button></nav>}
    </>}
  </>
}

export function EventDetailPage() {
  const { eventId } = useParams()
  const [event, setEvent] = useState(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    setEvent(null)
    setError('')
    api(`/events/${eventId}/`).then((result) => { if (active) setEvent(result.event) })
      .catch((err) => { if (active) setError(err.status === 404 ? 'This event could not be found.' : err.message) })
    return () => { active = false }
  }, [eventId, attempt])
  return <>
    <NavLink className="back-link" to="/events"><ArrowLeft size={16} /> All events</NavLink>
    {error ? <LoadError error={error} retry={() => setAttempt((value) => value + 1)} /> : !event ? <p role="status">Loading event…</p> : <article className="panel event-detail">
      <p className="kicker">NYU Engage</p><h1>{event.title}</h1>
      {event.status === 'cancelled' && <p className="study-notice study-notice--error" role="alert">This event has been cancelled.</p>}
      <p><strong>Starts:</strong> {formatDate(event.starts_at, true)}</p><p><strong>Ends:</strong> {formatDate(event.ends_at, true)}</p>
      <p><strong>Location:</strong> {event.location || 'See Engage for location'}</p><p><strong>Host:</strong> {event.host || 'NYU Engage'}</p>
      <p className="event-categories">{event.categories.join(' · ')}</p>
      <SaveEventButton key={`${event.id}-${event.is_saved}`} event={event} />
      <NavLink to="/calendar">View personal calendar</NavLink>
      <div className="event-description">{event.description || 'See the original event for details.'}</div>
      <a className="button button--primary" href={event.source_url} target="_blank" rel="noreferrer">View on NYU Engage <ExternalLink size={16} /></a>
      <p className="event-feed-note">Check Engage for current details and registration. Viewing this event does not RSVP.</p>
    </article>}
  </>
}
