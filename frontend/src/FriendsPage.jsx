import { useEffect, useState } from 'react'
import { Check, UserPlus, UserX, X } from 'lucide-react'

import { api } from './api'
import { displayName, initial } from './friends'

function FriendsHeader({ title, subtitle }) {
  return <header className="page-header">
    <div><p className="kicker">Connect</p><h1>{title}</h1><p className="page-header__subtitle">{subtitle}</p></div>
  </header>
}

function LoadError({ message, retry }) {
  return <div className="study-notice study-notice--error" role="alert"><p>{message}</p><button className="button button--secondary" onClick={retry}>Try again</button></div>
}

function PersonRow({ user, children }) {
  return <div className="friend-row">
    <div className="avatar">{initial(user)}</div>
    <div className="friend-row__copy">
      <strong>{displayName(user)}</strong>
      <small>{user.email}</small>
    </div>
    {children && <div className="friend-row__actions">{children}</div>}
  </div>
}

function FriendRow({ friend, onRemoved }) {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function remove() {
    setBusy(true)
    setError('')
    try {
      await api(`/social/friends/requests/${friend.friendship_id}/`, { method: 'DELETE' })
      onRemoved()
    } catch (err) {
      setError(err.message || 'Couldn’t remove. Try again.')
    } finally {
      setBusy(false)
    }
  }

  function cancel() {
    setConfirming(false)
    setError('')
  }

  return <div className="friend-row">
    <div className="avatar">{initial(friend)}</div>
    <div className="friend-row__copy">
      <strong>{displayName(friend)}</strong>
      <small>{friend.email}</small>
    </div>
    <div className={`friend-row__actions ${confirming ? 'friend-row__actions--confirm' : ''}`}>
      {confirming ? (
        <>
          <span role="alert" className={error ? 'friend-row__error' : ''}>{error || `Remove ${displayName(friend)} as a friend?`}</span>
          <button className="button button--danger button--small" onClick={remove} disabled={busy}>Remove</button>
          <button className="button button--secondary button--small" onClick={cancel} disabled={busy} autoFocus>Cancel</button>
        </>
      ) : (
        <button className="button button--secondary button--small" onClick={() => setConfirming(true)} aria-label={`Remove ${displayName(friend)} as a friend`}><UserX size={15} /> Remove</button>
      )}
    </div>
  </div>
}

export function FriendsPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [email, setEmail] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState('')
  const [message, setMessage] = useState('')
  const [busyId, setBusyId] = useState(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    api('/social/friends/').then((result) => { if (active) setData(result) })
      .catch((err) => { if (active) setLoadError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [attempt])

  async function sendRequest(event) {
    event.preventDefault()
    setSending(true)
    setSendError('')
    setMessage('')
    try {
      const result = await api('/social/friends/requests/', { method: 'POST', body: { email } })
      setEmail('')
      setMessage(result.friend_request.status === 'accepted'
        ? `You and ${displayName(result.friend_request.user)} are now friends — they had already sent you a request.`
        : `Friend request sent to ${displayName(result.friend_request.user)}.`)
      setAttempt((value) => value + 1)
    } catch (err) {
      setSendError(err.errors?.email?.[0] || err.message)
    } finally {
      setSending(false)
    }
  }

  async function respond(id, status) {
    setBusyId(id)
    setSendError('')
    setMessage('')
    try {
      await api(`/social/friends/requests/${id}/`, { method: 'PATCH', body: { status } })
      setAttempt((value) => value + 1)
    } catch (err) {
      setSendError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  async function cancel(id) {
    setBusyId(id)
    setSendError('')
    setMessage('')
    try {
      await api(`/social/friends/requests/${id}/`, { method: 'DELETE' })
      setAttempt((value) => value + 1)
    } catch (err) {
      setSendError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  return <>
    <FriendsHeader title="Friends" subtitle="Add classmates by their NYU email and manage your friend requests." />
    <form onSubmit={sendRequest} className="panel friends-add">
      <div className="panel__header"><div><p className="kicker">Add a friend</p><h2>Send a friend request</h2></div></div>
      <div className="friends-add__body">
        <label className={`field ${sendError ? 'field--error' : ''}`}>
          <span className="sr-only">Friend's NYU email address</span>
          <input
            type="email"
            required
            placeholder="name@nyu.edu"
            value={email}
            disabled={sending}
            onChange={(event) => { setEmail(event.target.value); setSendError(''); setMessage('') }}
          />
        </label>
        <button className="button button--primary" disabled={sending || !email}>
          <UserPlus size={17} /> {sending ? 'Sending…' : 'Send request'}
        </button>
      </div>
      {sendError && <p className="field__error friends-add__error" role="alert">{sendError}</p>}
    </form>
    {message && <div className="study-notice study-notice--success" role="status">{message}</div>}
    {loading ? <p role="status">Loading your friends…</p> : loadError ? <LoadError message={loadError} retry={() => setAttempt((value) => value + 1)} /> : data && <>
      {data.received_requests.length > 0 && <section className="panel panel--stacked" aria-label="Friend requests you've received">
        <div className="panel__header"><div><p className="kicker">Waiting on you</p><h2>Friend requests</h2></div><span className="count-pill">{data.received_requests.length}</span></div>
        <div className="friend-list">
          {data.received_requests.map((request) => <PersonRow user={request.user} key={request.id}>
            <button className="button button--soft button--small" disabled={busyId === request.id} aria-label={`Accept friend request from ${displayName(request.user)}`} onClick={() => respond(request.id, 'accepted')}><Check size={15} /> Accept</button>
            <button className="button button--secondary button--small" disabled={busyId === request.id} aria-label={`Decline friend request from ${displayName(request.user)}`} onClick={() => respond(request.id, 'declined')}><X size={15} /> Decline</button>
          </PersonRow>)}
        </div>
      </section>}
      {data.sent_requests.length > 0 && <section className="panel panel--stacked" aria-label="Friend requests you've sent">
        <div className="panel__header"><div><p className="kicker">Pending</p><h2>Sent requests</h2></div><span className="count-pill">{data.sent_requests.length}</span></div>
        <div className="friend-list">
          {data.sent_requests.map((request) => <PersonRow user={request.user} key={request.id}>
            <button className="button button--secondary button--small" disabled={busyId === request.id} aria-label={`Cancel friend request to ${displayName(request.user)}`} onClick={() => cancel(request.id)}><UserX size={15} /> Cancel</button>
          </PersonRow>)}
        </div>
      </section>}
      <section className="panel panel--stacked" aria-label="Your friends">
        <div className="panel__header"><div><p className="kicker">Connected</p><h2>Your friends</h2></div><span className="count-pill">{data.friends.length}</span></div>
        {data.friends.length ? <div className="friend-list">
          {data.friends.map((friend) => <FriendRow friend={friend} key={friend.id} onRemoved={() => setAttempt((value) => value + 1)} />)}
        </div> : <div className="empty-state"><span><UserPlus size={22} /></span><h3>No friends yet</h3><p>Send a friend request using a classmate's NYU email to get started.</p></div>}
      </section>
    </>}
  </>
}
