import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Bookmark, BookmarkCheck, MapPin, MessageSquare, Send, Share2, Star, Utensils } from 'lucide-react'

import { api, formatDate } from './api'
import { displayName, initial } from './friends'

const EMPTY_POST = { place_name: '', description: '', location: '', cuisine: '', rating: '' }
// #47: long recommendations are shortened in the feed so it stays easy to
// scan; the post's own page shows the whole thing.
export const PREVIEW_LENGTH = 280

export function previewText(text) {
  if (text.length <= PREVIEW_LENGTH) return text
  return `${text.slice(0, PREVIEW_LENGTH).trimEnd()}…`
}

function FeedField({ label, hint, error, children }) {
  return <label className={`field ${error ? 'field--error' : ''}`}>
    <span className="field__label">{label}{hint && <small>{hint}</small>}</span>
    {children}
    {error && <span className="field__error">{error}</span>}
  </label>
}

function LoadError({ message, retry }) {
  return <div className="study-notice study-notice--error" role="alert"><p>{message}</p><button className="button button--secondary" onClick={retry}>Try again</button></div>
}

// #53: save a post to try later, or unsave it. The button only changes once
// the server confirms, so what it shows is always what's stored.
function SaveButton({ post, onChange }) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function toggle() {
    setSaving(true)
    setError('')
    try {
      const result = await api(`/social/posts/${post.id}/save/`, { method: post.is_saved ? 'DELETE' : 'PUT' })
      onChange({ ...post, is_saved: result.saved })
    } catch (err) {
      setError(err.message || 'Could not update your saved recommendations.')
    } finally {
      setSaving(false)
    }
  }

  const Icon = post.is_saved ? BookmarkCheck : Bookmark
  return <div className="food-post__save">
    <button type="button" className={`button ${post.is_saved ? 'button--soft' : 'button--secondary'}`} aria-pressed={post.is_saved} aria-label={`${post.is_saved ? 'Unsave' : 'Save'} ${post.place_name}`} disabled={saving} onClick={toggle}>
      <Icon size={15} /> {post.is_saved ? 'Saved' : 'Save'}
    </button>
    {error && <span className="field__error" role="alert">{error}</span>}
  </div>
}

// #22: share a post with a friend. It's sent as a message in your
// conversation with them, with an optional note.
function SharePanel({ post, onClose }) {
  const [friends, setFriends] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [friendId, setFriendId] = useState('')
  const [note, setNote] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [sharedWith, setSharedWith] = useState(null)

  useEffect(() => {
    let active = true
    setFriends(null)
    setLoadError('')
    api('/social/friends/').then((result) => { if (active) setFriends(result.friends) })
      .catch((err) => { if (active) setLoadError(err.message) })
    return () => { active = false }
  }, [attempt])

  async function share(event) {
    event.preventDefault()
    if (!friendId || sending) return
    setSending(true)
    setError('')
    try {
      await api(`/social/posts/${post.id}/share/`, { method: 'POST', body: { friend_id: Number(friendId), note: note.trim() } })
      setSharedWith(friends.find((friend) => String(friend.id) === friendId))
    } catch (err) {
      setError(err.errors?.friend_id?.[0] || err.errors?.note?.[0] || err.message)
    } finally {
      setSending(false)
    }
  }

  return <section className="food-post__share" aria-label={`Share ${post.place_name}`}>
    {loadError ? <LoadError message={loadError} retry={() => setAttempt((value) => value + 1)} />
      : friends === null ? <p role="status">Loading your friends…</p>
        : sharedWith ? <div className="study-notice study-notice--success" role="status">
          <p>Shared with {displayName(sharedWith)}.</p>
          <div className="food-post__share-actions">
            <Link className="button button--soft button--small" to={`/messages/${sharedWith.id}`}>Open conversation</Link>
            <button type="button" className="button button--secondary button--small" onClick={onClose}>Done</button>
          </div>
        </div>
          : !friends.length ? <div className="food-post__share-empty">
            <p>Add a friend to share posts with them.</p>
            <div className="food-post__share-actions">
              <Link className="button button--soft button--small" to="/friends">Find friends</Link>
              <button type="button" className="button button--secondary button--small" onClick={onClose}>Cancel</button>
            </div>
          </div>
            : <form onSubmit={share}>
              <label className="field">
                <span className="field__label">Share with</span>
                <select value={friendId} disabled={sending} onChange={(event) => { setFriendId(event.target.value); setError('') }}>
                  <option value="">Choose a friend</option>
                  {friends.map((friend) => <option key={friend.id} value={friend.id}>{displayName(friend)}</option>)}
                </select>
              </label>
              <label className="field">
                <span className="field__label">Note<small>Optional</small></span>
                <textarea value={note} rows={2} maxLength={2000} disabled={sending} placeholder="Why should they try it?"
                  onChange={(event) => { setNote(event.target.value); setError('') }} />
              </label>
              {error && <p className="field__error" role="alert">{error}</p>}
              <div className="food-post__share-actions">
                <button className="button button--primary button--small" type="submit" disabled={!friendId || sending}><Send size={14} /> {sending ? 'Sharing…' : 'Share'}</button>
                <button type="button" className="button button--secondary button--small" onClick={onClose} disabled={sending}>Cancel</button>
              </div>
            </form>}
  </section>
}

function FoodPostCard({ post, full = false, onChange }) {
  const [sharing, setSharing] = useState(false)
  const shortened = !full && post.description.length > PREVIEW_LENGTH
  const Heading = full ? 'h1' : 'h3'
  return <article className={`food-post ${full ? 'food-post--full' : ''}`} aria-label={post.place_name}>
    <div className="food-post__header">
      <div>
        <Heading>{full ? post.place_name : <Link to={`/community/posts/${post.id}`}>{post.place_name}</Link>}</Heading>
        {(post.cuisine || post.location) && <p className="food-post__meta">
          {post.cuisine && <span>{post.cuisine}</span>}
          {post.location && <span><MapPin size={13} /> {post.location}</span>}
        </p>}
      </div>
      {post.rating && <span className="count-pill" aria-label={`Rated ${post.rating} out of 5`}><Star size={12} /> {post.rating}/5</span>}
    </div>
    <p className="food-post__description">{full ? post.description : previewText(post.description)}</p>
    {shortened && <Link className="food-post__more" to={`/community/posts/${post.id}`} aria-label={`Read more about ${post.place_name}`}>Read more</Link>}
    <footer className="food-post__footer">
      <div className="food-post__author">
        <div className="avatar">{post.author.profile_picture ? <img src={post.author.profile_picture} alt="" /> : initial(post.author)}</div>
        <span>{displayName(post.author)} · {formatDate(post.created_at, true)}</span>
      </div>
      <div className="food-post__actions">
        <button type="button" className="button button--secondary food-post__share-toggle" aria-expanded={sharing} aria-label={`Share ${post.place_name} with a friend`} onClick={() => setSharing((value) => !value)}>
          <Share2 size={15} /> Share
        </button>
        {onChange && <SaveButton post={post} onChange={onChange} />}
      </div>
    </footer>
    {sharing && <SharePanel post={post} onClose={() => setSharing(false)} />}
  </article>
}

// #47: one post on its own page, with room for comments (#49 adds them).
export function FoodPostPage() {
  const { postId } = useParams()
  const [post, setPost] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [missing, setMissing] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    setMissing(false)
    api(`/social/posts/${postId}/`).then((result) => { if (active) setPost(result.post) })
      .catch((err) => {
        if (!active) return
        if (err.status === 404) setMissing(true)
        else setError(err.message)
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [postId, attempt])

  return <>
    <Link className="back-link" to="/community"><ArrowLeft size={16} /> Back to food feed</Link>
    {loading ? <p role="status">Loading the post…</p>
      : missing ? <div className="empty-state"><span><Utensils size={22} /></span><h3>This post isn’t available</h3><p>It may have been removed.</p><Link className="button button--soft" to="/community">Browse the food feed</Link></div>
        : error ? <LoadError message={error} retry={() => setAttempt((value) => value + 1)} />
          : post && <>
            <section className="panel" aria-label="Post"><FoodPostCard post={post} full onChange={setPost} /></section>
            <section className="panel panel--stacked food-post-comments" aria-labelledby="comments-heading">
              <div className="panel__header"><div><h2 id="comments-heading">Comments</h2></div></div>
              <div className="empty-state"><span><MessageSquare size={22} /></span><h3>No comments yet</h3></div>
            </section>
          </>}
  </>
}

// #46: create a food post and see it appear in the community feed. Browsing
// and filtering the feed is #47; photos come after #84's upload setup is
// reused.
export function FoodFeedPage() {
  const [posts, setPosts] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [values, setValues] = useState(EMPTY_POST)
  const [errors, setErrors] = useState({})
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    api('/social/posts/').then((result) => { if (active) setPosts(result.posts) })
      .catch((err) => { if (active) setLoadError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [attempt])

  function replacePost(updated) {
    setPosts((current) => current.map((item) => (item.id === updated.id ? updated : item)))
  }

  function update(event) {
    setValues((current) => ({ ...current, [event.target.name]: event.target.value }))
    setErrors((current) => ({ ...current, [event.target.name]: undefined }))
    setMessage('')
  }

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    setSubmitError('')
    setMessage('')
    try {
      const result = await api('/social/posts/', {
        method: 'POST',
        body: { ...values, rating: values.rating ? Number(values.rating) : null },
      })
      setPosts((current) => [result.post, ...(current || [])])
      setValues(EMPTY_POST)
      setMessage(`Posted your recommendation for ${result.post.place_name}.`)
    } catch (err) {
      setErrors(err.errors || {})
      if (!Object.keys(err.errors || {}).length) setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return <>
    <header className="page-header">
      <div><p className="kicker">Community</p><h1>Food feed</h1><p className="page-header__subtitle">Share a place to eat and see what other students recommend.</p></div>
      <Link className="button button--secondary" to="/community/saved"><Bookmark size={16} /> Saved recommendations</Link>
    </header>
    <form onSubmit={submit} className="editor-card food-post-form" aria-label="Create a food post">
      <FeedField label="Restaurant or food place" error={errors.place_name?.[0]}>
        <input name="place_name" value={values.place_name} onChange={update} placeholder="e.g. Mamoun's Falafel" maxLength={200} required />
      </FeedField>
      <FeedField label="Description or recommendation" error={errors.description?.[0]}>
        <textarea name="description" value={values.description} onChange={update} rows={3} placeholder="What should people order? Why do you like it?" required />
      </FeedField>
      <div className="field-pair">
        <FeedField label="Cuisine" hint="Optional" error={errors.cuisine?.[0]}>
          <input name="cuisine" value={values.cuisine} onChange={update} placeholder="e.g. Middle Eastern" maxLength={100} />
        </FeedField>
        <FeedField label="Rating" hint="Optional" error={errors.rating?.[0]}>
          <select name="rating" value={values.rating} onChange={update}>
            <option value="">No rating</option>
            {[5, 4, 3, 2, 1].map((value) => <option key={value} value={value}>{value} / 5</option>)}
          </select>
        </FeedField>
      </div>
      <FeedField label="Location" hint="Optional" error={errors.location?.[0]}>
        <input name="location" value={values.location} onChange={update} placeholder="e.g. 119 Macdougal St" maxLength={200} />
      </FeedField>
      {submitError && <p className="field__error" role="alert">{submitError}</p>}
      <div className="form-actions">
        <button className="button button--primary" disabled={submitting}><Send size={16} /> {submitting ? 'Posting…' : 'Post'}</button>
      </div>
    </form>
    {message && <div className="study-notice study-notice--success food-post-notice" role="status">{message}</div>}
    {loading ? <p role="status">Loading the food feed…</p> : loadError ? <LoadError message={loadError} retry={() => setAttempt((value) => value + 1)} /> : posts && <section className="panel panel--stacked" aria-label="Food feed">
      <div className="panel__header"><div><p className="kicker">Latest first</p><h2>Recommendations</h2></div><span className="count-pill">{posts.length}</span></div>
      {posts.length ? <div className="food-post-list">
        {posts.map((post) => <FoodPostCard post={post} key={post.id} onChange={replacePost} />)}
      </div> : <div className="empty-state"><span><Utensils size={22} /></span><h3>No posts yet</h3><p>Be the first to recommend a place to eat.</p></div>}
    </section>}
  </>
}

// #53: the student's saved recommendations, most recently saved first.
// Unsaving one here takes it off the list.
export function SavedPostsPage() {
  const [posts, setPosts] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    api('/social/posts/saved/').then((result) => { if (active) setPosts(result.posts) })
      .catch((err) => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [attempt])

  function changed(updated) {
    setPosts((current) => (updated.is_saved
      ? current.map((item) => (item.id === updated.id ? updated : item))
      : current.filter((item) => item.id !== updated.id)))
  }

  return <>
    <Link className="back-link" to="/community"><ArrowLeft size={16} /> Back to food feed</Link>
    <header className="page-header">
      <div><p className="kicker">Community</p><h1>Saved recommendations</h1><p className="page-header__subtitle">Places you saved to try later. Only you can see this list.</p></div>
    </header>
    {loading ? <p role="status">Loading your saved recommendations…</p>
      : error ? <LoadError message={error} retry={() => setAttempt((value) => value + 1)} />
        : posts && <section className="panel panel--stacked" aria-label="Saved recommendations">
          <div className="panel__header"><div><p className="kicker">Most recently saved first</p><h2>Saved places</h2></div><span className="count-pill">{posts.length}</span></div>
          {posts.length ? <div className="food-post-list">
            {posts.map((post) => <FoodPostCard post={post} key={post.id} onChange={changed} />)}
          </div> : <div className="empty-state"><span><Bookmark size={22} /></span><h3>No saved recommendations yet</h3><p>Save a post from the food feed to find it here later.</p><Link className="button button--soft" to="/community">Browse the food feed</Link></div>}
        </section>}
  </>
}
