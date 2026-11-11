import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, MessageCircle, Send } from 'lucide-react'

import { api, formatDate } from './api'
import { displayName, initial } from './friends'

function ErrorNotice({ text, retry }) {
  return <div className="study-notice study-notice--error" role="alert">
    <p>{text}</p>
    {retry && <button className="button button--secondary" type="button" onClick={retry}>Try again</button>}
  </div>
}

export function MessagesPage() {
  const [friends, setFriends] = useState(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setFriends(null)
    setError('')
    api('/social/friends/')
      .then((data) => { if (active) setFriends(data.friends) })
      .catch((err) => { if (active) setError(err.message) })
    return () => { active = false }
  }, [attempt])

  return <>
    <header className="page-header">
      <div><p className="kicker">Connect</p><h1>Messages</h1><p className="page-header__subtitle">Start or continue a private conversation with a friend.</p></div>
    </header>
    {error ? <ErrorNotice text={error} retry={() => setAttempt((n) => n + 1)} /> : friends === null ? <p role="status">Loading conversations…</p> : (
      <section className="panel panel--stacked" aria-label="Your conversations">
        <div className="panel__header"><div><p className="kicker">Your contacts</p><h2>Conversations</h2></div><span className="count-pill">{friends.length}</span></div>
        {friends.length ? <div className="friend-list">
          {friends.map((friend) => <Link key={friend.id} className="friend-row friend-row--conversation" to={`/messages/${friend.id}`} aria-label={`Open conversation with ${displayName(friend)}`}>
            <span className="avatar">{friend.profile_picture ? <img src={friend.profile_picture} alt="" /> : initial(friend)}</span>
            <span className="friend-row__copy"><strong>{displayName(friend)}</strong><small>{friend.email}</small></span>
            <MessageCircle size={18} aria-hidden="true" />
          </Link>)}
        </div> : <div className="empty-state"><span><MessageCircle size={22} /></span><h3>No conversations yet</h3><p>Add a friend to start messaging.</p><Link className="button button--soft" to="/friends">Find friends</Link></div>}
      </section>
    )}
  </>
}

export function ConversationPage() {
  const { userId } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    setData(null)
    setDraft('')
    setSendError('')
    api(`/social/messages/${userId}/`)
      .then((result) => { if (active) setData(result) })
      .catch((err) => { if (active) setError(err.status === 404 ? 'This conversation is not available. You can only message current friends.' : err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [userId, attempt])

  async function sendMessage(event) {
    event.preventDefault()
    const body = draft.trim()
    if (!body || sending) return
    setSending(true)
    setSendError('')
    try {
      const result = await api(`/social/messages/${userId}/`, { method: 'POST', body: { body } })
      setData((current) => current ? { ...current, messages: [...current.messages, result.message] } : current)
      setDraft('')
    } catch (err) {
      setSendError(err.errors?.body?.[0] || err.message)
    } finally {
      setSending(false)
    }
  }

  return <>
    <Link className="back-link" to="/messages"><ArrowLeft size={16} /> Back to messages</Link>
    {loading ? <p role="status">Loading conversation…</p>
      : error ? <ErrorNotice text={error} retry={() => setAttempt((n) => n + 1)} />
        : data && <>
          <header className="page-header"><div><p className="kicker">Private conversation</p><h1>{displayName(data.friend)}</h1><p className="page-header__subtitle">{data.friend.email}</p></div></header>
          <section className="panel conversation" aria-label={`Conversation with ${displayName(data.friend)}`}>
            <div className="conversation__history" role="log" aria-label="Message history" aria-live="polite">
              {data.messages.length ? data.messages.map((message) => <article key={message.id} className={`conversation__message ${message.is_mine ? 'conversation__message--mine' : ''}`}>
                <strong>{message.is_mine ? 'You' : message.sender_name}</strong>
                <p>{message.body}</p>
                <time dateTime={message.created_at}>{formatDate(message.created_at, true)}</time>
              </article>) : <div className="empty-state"><span><MessageCircle size={22} /></span><h3>No messages yet</h3><p>Say hello to start your conversation.</p></div>}
            </div>
            <form className="conversation__compose" onSubmit={sendMessage}>
              <label htmlFor="conversation-draft">Your message</label>
              <textarea id="conversation-draft" value={draft} rows={3} maxLength={2000} placeholder="Write a message…" disabled={sending}
                onChange={(event) => { setDraft(event.target.value); setSendError('') }} />
              {sendError && <p role="alert" className="field__error">{sendError}</p>}
              <button className="button button--primary" type="submit" disabled={!draft.trim() || sending}><Send size={16} /> {sending ? 'Sending…' : 'Send message'}</button>
            </form>
          </section>
        </>}
  </>
}
