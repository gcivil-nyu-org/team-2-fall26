import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, MapPin, MessageSquare, Pencil, Save, Send, Star, Trash2, Utensils } from 'lucide-react'

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

function FoodPostCard({ post, full = false }) {
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
    <footer className="food-post__author">
      <div className="avatar">{post.author.profile_picture ? <img src={post.author.profile_picture} alt="" /> : initial(post.author)}</div>
      <span>{displayName(post.author)} · {formatDate(post.created_at, true)}</span>
    </footer>
  </article>
}

// #47: one post on its own page, with room for comments (#49 adds them).
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
              <FoodPostCard post={post} full />
              {/* #51/#52: only the author sees these; the server checks too. */}
              {post.is_author && <div className="food-post__actions">
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
            <section className="panel panel--stacked food-post-comments" aria-labelledby="comments-heading">
              <div className="panel__header"><div><h2 id="comments-heading">Comments</h2></div></div>
              <div className="empty-state"><span><MessageSquare size={22} /></span><h3>No comments yet</h3></div>
            </section>
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

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    api('/social/posts/').then((result) => { if (active) setPosts(result.posts) })
      .catch((err) => { if (active) setLoadError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [attempt])

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
    </header>
    <form onSubmit={submit} className="editor-card food-post-form" aria-label="Create a food post">
      <FoodPostFields values={values} errors={errors} update={update} />
      {submitError && <p className="field__error" role="alert">{submitError}</p>}
      <div className="form-actions">
        <button className="button button--primary" disabled={submitting}><Send size={16} /> {submitting ? 'Posting…' : 'Post'}</button>
      </div>
    </form>
    {message && <div className="study-notice study-notice--success food-post-notice" role="status">{message}</div>}
    {loading ? <p role="status">Loading the food feed…</p> : loadError ? <LoadError message={loadError} retry={() => setAttempt((value) => value + 1)} /> : posts && <section className="panel panel--stacked" aria-label="Food feed">
      <div className="panel__header"><div><p className="kicker">Latest first</p><h2>Recommendations</h2></div><span className="count-pill">{posts.length}</span></div>
      {posts.length ? <div className="food-post-list">
        {posts.map((post) => <FoodPostCard post={post} key={post.id} />)}
      </div> : <div className="empty-state"><span><Utensils size={22} /></span><h3>No posts yet</h3><p>Be the first to recommend a place to eat.</p></div>}
    </section>}
  </>
}
