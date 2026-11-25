import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Bookmark, BookmarkCheck, Flag, Heart, MapPin, Search, MessageSquare, Pencil, Save, Send, Share2, Star, Trash2, Utensils } from 'lucide-react'

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

// #48: search the current community feed without changing the order or
// exposing posts outside the authenticated, active-author feed.
export function filterFoodPosts(posts, { query = '', cuisine = '', location = '' } = {}) {
  const term = query.trim().toLocaleLowerCase()
  const kind = cuisine.trim().toLocaleLowerCase()
  const place = location.trim().toLocaleLowerCase()
  return posts.filter((post) => (
    (!term || [post.place_name, post.description].some((value) => (value || '').toLocaleLowerCase().includes(term))) &&
    (!kind || (post.cuisine || '').toLocaleLowerCase() === kind) &&
    (!place || (post.location || '').toLocaleLowerCase().includes(place))
  ))
}

function FeedField({ label, hint, error, children }) {
  return <label className={`field ${error ? 'field--error' : ''}`}>
    <span className="field__label">{label}{hint && <small>{hint}</small>}</span>
    {children}
    {error && <span className="field__error">{error}</span>}
  </label>
}

// #46 create and #51 edit use the same fields, so both forms stay in step.
function FoodPostFields({ values, errors, update }) {
  return <>
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
  </>
}

function postBody(values) {
  return { ...values, rating: values.rating ? Number(values.rating) : null }
}

function NotAvailable() {
  return <div className="empty-state"><span><Utensils size={22} /></span><h3>This post isn’t available</h3><p>It may have been removed.</p><Link className="button button--soft" to="/community">Browse the food feed</Link></div>
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
      onChange({ id: post.id, is_saved: result.saved })
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

// #67: the reasons a student can pick when reporting a post or comment.
export const REPORT_REASONS = [
  ['spam', 'Spam'],
  ['harassment', 'Harassment or bullying'],
  ['inappropriate', 'Inappropriate content'],
  ['other', 'Something else'],
]
const REPORT_CONFIRMATION = 'Thanks, your report was sent to the moderators.'

// #67: pick a reason (and optionally add details) and send the report.
// Reporting never hides anything; it only tells the moderators.
function ReportPanel({ label, kind, url, onReported, onClose }) {
  const [reason, setReason] = useState('')
  const [details, setDetails] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    if (!reason || sending) return
    setSending(true)
    setError('')
    try {
      await api(url, { method: 'POST', body: { reason, details: details.trim() } })
      onReported()
    } catch (err) {
      // Already reported (say, from another tab): the end result is the same.
      if (err.status === 409) onReported()
      else {
        setError(err.errors?.reason?.[0] || err.errors?.details?.[0] || err.message)
        setSending(false)
      }
    }
  }

  return <form className="report-panel" aria-label={`Report ${label}`} onSubmit={submit}>
    <fieldset disabled={sending}>
      <legend>Why are you reporting this {kind}?</legend>
      {REPORT_REASONS.map(([value, text]) => <label key={value} className="report-panel__reason">
        <input type="radio" name="reason" value={value} checked={reason === value} onChange={() => { setReason(value); setError('') }} /> {text}
      </label>)}
      <label className="field">
        <span className="field__label">Details<small>Optional</small></span>
        <textarea value={details} rows={2} maxLength={500} placeholder="Anything the moderators should know?" onChange={(event) => { setDetails(event.target.value); setError('') }} />
      </label>
    </fieldset>
    <p className="report-panel__note">The {kind} stays visible while the moderators review it.</p>
    {error && <p className="field__error" role="alert">{error}</p>}
    <div className="report-panel__actions">
      <button className="button button--primary button--small" type="submit" disabled={!reason || sending}><Flag size={14} /> {sending ? 'Sending…' : 'Send report'}</button>
      <button className="button button--secondary button--small" type="button" onClick={onClose} disabled={sending}>Cancel</button>
    </div>
  </form>
}

// #67: the Report toggle, or "Reported" once this student has reported it.
function ReportToggle({ label, reported, open, onToggle, className = '' }) {
  if (reported) return <span className={`report-toggle report-toggle--done ${className}`}><Flag size={13} aria-hidden="true" /> Reported</span>
  return <button type="button" className={`report-toggle ${className}`} aria-expanded={open} aria-label={`Report ${label}`} onClick={onToggle}>
    <Flag size={13} aria-hidden="true" /> Report
  </button>
}

// #50: like/unlike a post; the server returns the authoritative count.
function LikeButton({ post, onChange }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function toggle() {
    setBusy(true)
    setError('')
    try {
      const result = await api(`/social/posts/${post.id}/like/`, { method: post.is_liked ? 'DELETE' : 'PUT' })
      onChange({ id: post.id, is_liked: result.is_liked, like_count: result.like_count })
    } catch (err) {
      setError(err.message || 'Could not update your like.')
    } finally {
      setBusy(false)
    }
  }

  return <div className="food-post__like">
    <button type="button" className={`button ${post.is_liked ? 'button--soft' : 'button--secondary'}`}
      aria-pressed={Boolean(post.is_liked)} aria-label={`${post.is_liked ? 'Unlike' : 'Like'} ${post.place_name}`}
      disabled={busy} onClick={toggle}>
      <Heart size={15} fill={post.is_liked ? 'currentColor' : 'none'} aria-hidden="true" />
      {post.like_count || 0} {post.like_count === 1 ? 'like' : 'likes'}
    </button>
    {error && <span className="field__error" role="alert">{error}</span>}
  </div>
}

function FoodPostCard({ post, full = false, onChange }) {
  // Share and Report open one panel at a time under the card.
  const [panel, setPanel] = useState(null)
  const [reported, setReported] = useState(Boolean(post.is_reported))
  const [reportNotice, setReportNotice] = useState(false)
  const sharing = panel === 'share'
  const togglePanel = (name) => setPanel((current) => (current === name ? null : name))
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
        {!full && <Link className="food-post__comments-link" to={`/community/posts/${post.id}`} aria-label={`${commentCountLabel(post.comment_count)} on ${post.place_name}`}><MessageSquare size={14} /> {commentCountLabel(post.comment_count)}</Link>}
        <button type="button" className="button button--secondary food-post__share-toggle" aria-expanded={sharing} aria-label={`Share ${post.place_name} with a friend`} onClick={() => togglePanel('share')}>
          <Share2 size={15} /> Share
        </button>
        {onChange && <LikeButton post={post} onChange={onChange} />}
        {onChange && <SaveButton post={post} onChange={onChange} />}
        {!post.is_author && <ReportToggle label={post.place_name} reported={reported} open={panel === 'report'} onToggle={() => togglePanel('report')} />}
      </div>
    </footer>
    {sharing && <SharePanel post={post} onClose={() => setPanel(null)} />}
    {panel === 'report' && <ReportPanel label={post.place_name} kind="post" url={`/social/posts/${post.id}/report/`}
      onReported={() => { setReported(true); setReportNotice(true); setPanel(null) }} onClose={() => setPanel(null)} />}
    {reportNotice && <p className="study-notice study-notice--success report-notice" role="status">{REPORT_CONFIRMATION}</p>}
  </article>
}

export function commentCountLabel(count) {
  if (!count) return 'No comments yet'
  return count === 1 ? '1 comment' : `${count} comments`
}

// #49: a post's comments, oldest first, with a box for adding one.
function CommentItem({ comment }) {
  const [reporting, setReporting] = useState(false)
  const [reported, setReported] = useState(Boolean(comment.is_reported))
  const [notice, setNotice] = useState(false)
  const label = `comment by ${displayName(comment.author)}`
  return <li className="food-comment">
    <div className="avatar">{comment.author.profile_picture ? <img src={comment.author.profile_picture} alt="" /> : initial(comment.author)}</div>
    <div className="food-comment__body">
      <p className="food-comment__meta"><strong>{displayName(comment.author)}</strong> · {formatDate(comment.created_at, true)}</p>
      <p className="food-comment__text">{comment.body}</p>
      {!comment.is_author && <ReportToggle className="report-toggle--comment" label={label} reported={reported} open={reporting} onToggle={() => setReporting((value) => !value)} />}
      {reporting && <ReportPanel label={label} kind="comment" url={`/social/comments/${comment.id}/report/`}
        onReported={() => { setReported(true); setNotice(true); setReporting(false) }} onClose={() => setReporting(false)} />}
      {notice && <p className="study-notice study-notice--success report-notice" role="status">{REPORT_CONFIRMATION}</p>}
    </div>
  </li>
}

function PostComments({ postId, onCountChange }) {
  const [comments, setComments] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const [posting, setPosting] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    api(`/social/posts/${postId}/comments/`).then((result) => { if (active) setComments(result.comments) })
      .catch((err) => { if (active) setLoadError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [postId, attempt])

  async function submit(event) {
    event.preventDefault()
    if (!draft.trim()) return
    setPosting(true)
    setError('')
    try {
      const result = await api(`/social/posts/${postId}/comments/`, { method: 'POST', body: { body: draft } })
      const next = [...comments, result.comment]
      setComments(next)
      onCountChange(next.length)
      setDraft('')
    } catch (err) {
      setError(err.errors?.body?.[0] || err.message)
    } finally {
      setPosting(false)
    }
  }

  return <section className="panel panel--stacked food-post-comments" aria-labelledby="comments-heading">
    <div className="panel__header"><div><h2 id="comments-heading">Comments</h2></div>{comments && <span className="count-pill">{comments.length}</span>}</div>
    {loading ? <p className="food-comments__status" role="status">Loading comments…</p>
      : loadError ? <LoadError message={loadError} retry={() => setAttempt((value) => value + 1)} />
        : comments && (comments.length ? <ol className="food-comments" aria-label="Comments on this post">
          {comments.map((comment) => <CommentItem comment={comment} key={comment.id} />)}
        </ol> : <div className="empty-state"><span><MessageSquare size={22} /></span><h3>No comments yet</h3><p>Be the first to share your thoughts.</p></div>)}
    {comments && <form className="food-comment-form" onSubmit={submit} aria-label="Write a comment">
      <div className={`field ${error ? 'field--error' : ''}`}>
        <label className="field__label" htmlFor={`comment-${postId}`}>Add a comment</label>
        <textarea id={`comment-${postId}`} name="body" rows={3} maxLength={1000} value={draft} placeholder="What did you think?" aria-describedby={error ? `comment-${postId}-error` : undefined} aria-invalid={Boolean(error)} onChange={(event) => { setDraft(event.target.value); setError('') }} />
        {error && <span className="field__error" id={`comment-${postId}-error`} role="alert">{error}</span>}
      </div>
      <div className="form-actions">
        <button className="button button--primary" disabled={posting || !draft.trim()}><Send size={16} /> {posting ? 'Posting…' : 'Post comment'}</button>
      </div>
    </form>}
  </section>
}

// #47: one post on its own page, with its comments (#49).
export function FoodPostPage() {
  const { postId } = useParams()
  const navigate = useNavigate()
  const notice = useLocation().state?.notice
  const [post, setPost] = useState(null)
  // #52: deleting asks first, in the same style as deleting a course.
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
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

  async function remove() {
    setDeleting(true)
    setDeleteError('')
    try {
      await api(`/social/posts/${post.id}/`, { method: 'DELETE' })
      navigate('/community', { state: { notice: `Deleted your post about ${post.place_name}.` } })
    } catch {
      setDeleteError('Couldn’t delete this post. Try again.')
      setDeleting(false)
    }
  }

  function cancelDelete() {
    setConfirming(false)
    setDeleteError('')
  }

  return <>
    <Link className="back-link" to="/community"><ArrowLeft size={16} /> Back to food feed</Link>
    {notice && !loading && post && <div className="study-notice study-notice--success food-post-notice" role="status">{notice}</div>}
    {loading ? <p role="status">Loading the post…</p>
      : missing ? <NotAvailable />
        : error ? <LoadError message={error} retry={() => setAttempt((value) => value + 1)} />
          : post && <>
            <section className="panel" aria-label="Post">
              <FoodPostCard post={post} full onChange={(changes) => setPost((current) => ({ ...current, ...changes }))} />
              {/* #51/#52: only the author sees these; the server checks too. */}
              {post.is_author && <div className="food-post__owner-actions">
                <Link className="button button--secondary button--small" to={`/community/posts/${post.id}/edit`}><Pencil size={15} /> Edit post</Link>
                <button className="button button--secondary button--small" onClick={() => setConfirming(true)} disabled={confirming}><Trash2 size={15} /> Delete post</button>
              </div>}
              {confirming && <div className="delete-confirm" role="alert">
                <p className={deleteError ? 'delete-confirm__error' : ''}>{deleteError || `Delete your post about ${post.place_name}? This can’t be undone.`}</p>
                <div>
                  <button className="button button--danger button--small" onClick={remove} disabled={deleting}>Delete</button>
                  <button className="button button--secondary button--small" onClick={cancelDelete} disabled={deleting} autoFocus>Cancel</button>
                </div>
              </div>}
            </section>
            <PostComments postId={post.id} onCountChange={(count) => setPost((current) => ({ ...current, comment_count: count }))} />
          </>}
  </>
}

// #51: edit your own post with the same fields used to create it.
export function FoodPostEditPage() {
  const { postId } = useParams()
  const navigate = useNavigate()
  const [values, setValues] = useState(null)
  const [placeName, setPlaceName] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [missing, setMissing] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [errors, setErrors] = useState({})
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const postUrl = `/community/posts/${postId}`

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    setMissing(false)
    api(`/social/posts/${postId}/`).then(({ post }) => {
      if (!active) return
      // Someone else's post can be read but not edited.
      if (!post.is_author) return setMissing(true)
      setPlaceName(post.place_name)
      setValues({
        place_name: post.place_name,
        description: post.description,
        location: post.location,
        cuisine: post.cuisine,
        rating: post.rating ? String(post.rating) : '',
      })
    }).catch((err) => {
      if (!active) return
      if (err.status === 404) setMissing(true)
      else setLoadError(err.message)
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [postId, attempt])

  function update(event) {
    setValues((current) => ({ ...current, [event.target.name]: event.target.value }))
    setErrors((current) => ({ ...current, [event.target.name]: undefined }))
  }

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    setSubmitError('')
    try {
      await api(`/social/posts/${postId}/`, { method: 'PATCH', body: postBody(values) })
      navigate(postUrl, { state: { notice: 'Saved your changes.' } })
    } catch (err) {
      setSubmitting(false)
      if (err.status === 404) return setMissing(true)
      setErrors(err.errors || {})
      if (!Object.keys(err.errors || {}).length) setSubmitError(err.message)
    }
  }

  return <>
    <Link className="back-link" to={postUrl}><ArrowLeft size={16} /> Back to post</Link>
    {loading ? <p role="status">Loading the post…</p>
      : missing ? <NotAvailable />
        : loadError ? <LoadError message={loadError} retry={() => setAttempt((value) => value + 1)} />
          : values && <>
            <header className="page-header">
              <div><p className="kicker">Community</p><h1>Edit post</h1><p className="page-header__subtitle">Update your recommendation for {placeName}.</p></div>
            </header>
            <form onSubmit={submit} className="editor-card food-post-form" aria-label="Edit your food post">
              <FoodPostFields values={values} errors={errors} update={update} />
              {submitError && <p className="field__error" role="alert">{submitError}</p>}
              <div className="form-actions">
                <Link className="button button--secondary" to={postUrl}>Cancel</Link>
                <button className="button button--primary" disabled={submitting}><Save size={16} /> {submitting ? 'Saving…' : 'Save changes'}</button>
              </div>
            </form>
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
  // #52: after deleting a post you land here with a note saying so.
  const [message, setMessage] = useState(useLocation().state?.notice || '')
  const [filters, setFilters] = useState({ query: '', cuisine: '', location: '' })

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
    setPosts((current) => current.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)))
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
        body: postBody(values),
      })
      setPosts((current) => [result.post, ...(current || [])])
      setFilters({ query: '', cuisine: '', location: '' })
      setValues(EMPTY_POST)
      setMessage(`Posted your recommendation for ${result.post.place_name}.`)
    } catch (err) {
      setErrors(err.errors || {})
      if (!Object.keys(err.errors || {}).length) setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const visible = posts ? filterFoodPosts(posts, filters) : []
  const cuisines = posts ? [...new Set(posts.map((post) => post.cuisine?.trim()).filter(Boolean))]
    .sort((left, right) => left.localeCompare(right)) : []
  const filtering = Object.values(filters).some((value) => value.trim())

  return <>
    <header className="page-header">
      <div><p className="kicker">Community</p><h1>Food feed</h1><p className="page-header__subtitle">Share a place to eat and see what other students recommend.</p></div>
      <Link className="button button--secondary" to="/community/saved"><Bookmark size={16} /> Saved recommendations</Link>
    </header>
    <form onSubmit={submit} className="editor-card food-post-form" aria-label="Create a food post">
      <FoodPostFields values={values} errors={errors} update={update} />
      {submitError && <p className="field__error" role="alert">{submitError}</p>}
      <div className="form-actions">
        <button className="button button--primary" disabled={submitting}><Send size={16} /> {submitting ? 'Posting…' : 'Post'}</button>
      </div>
    </form>
    {message && <div className="study-notice study-notice--success food-post-notice" role="status">{message}</div>}
    {posts?.length > 0 && <section className="panel panel--stacked food-feed-filters" aria-label="Filter food recommendations">
      <div className="panel__header"><div><p className="kicker">Find a place</p><h2>Search &amp; filter</h2></div>
        {filtering && <button type="button" className="button button--secondary button--small" onClick={() => setFilters({ query: '', cuisine: '', location: '' })}>Clear filters</button>}
      </div>
      <div className="food-feed-filters__fields">
        <label className="field"><span className="field__label">Search recommendations</span>
          <div className="food-feed-filters__search"><Search size={17} aria-hidden="true" /><input type="search" value={filters.query} placeholder="Search place or keyword" onChange={(event) => setFilters((current) => ({ ...current, query: event.target.value }))} /></div>
        </label>
        <label className="field"><span className="field__label">Filter by cuisine</span>
          <select value={filters.cuisine} onChange={(event) => setFilters((current) => ({ ...current, cuisine: event.target.value }))}>
            <option value="">All cuisines</option>
            {cuisines.map((cuisine) => <option key={cuisine} value={cuisine}>{cuisine}</option>)}
          </select>
        </label>
        <label className="field"><span className="field__label">Filter by location</span>
          <input value={filters.location} placeholder="e.g. Brooklyn" onChange={(event) => setFilters((current) => ({ ...current, location: event.target.value }))} />
        </label>
      </div>
    </section>}
    {loading ? <p role="status">Loading the food feed…</p> : loadError ? <LoadError message={loadError} retry={() => setAttempt((value) => value + 1)} /> : posts && <section className="panel panel--stacked" aria-label="Food feed">
      <div className="panel__header"><div><p className="kicker">Latest first</p><h2>Recommendations</h2></div><span className="count-pill" aria-label={`${visible.length} matching recommendations`}>{visible.length}</span></div>
      {visible.length ? <div className="food-post-list">
        {visible.map((post) => <FoodPostCard post={post} key={post.id} onChange={replacePost} />)}
      </div> : <div className="empty-state"><span><Utensils size={22} /></span><h3>{posts.length ? 'No matching recommendations' : 'No posts yet'}</h3><p>{posts.length ? 'Try another keyword, cuisine, or location.' : 'Be the first to recommend a place to eat.'}</p></div>}
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
    setPosts((current) => (updated.is_saved === false
      ? current.filter((item) => item.id !== updated.id)
      : current.map((item) => (item.id === updated.id ? { ...item, ...updated } : item))))
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
