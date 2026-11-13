import { useEffect, useState } from 'react'
import { MapPin, Send, Star, Utensils } from 'lucide-react'

import { api, formatDate } from './api'
import { displayName, initial } from './friends'

const EMPTY_POST = { place_name: '', description: '', location: '', cuisine: '', rating: '' }

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

function FoodPostCard({ post }) {
  return <article className="food-post" aria-label={post.place_name}>
    <div className="food-post__header">
      <div>
        <h3>{post.place_name}</h3>
        {(post.cuisine || post.location) && <p className="food-post__meta">
          {post.cuisine && <span>{post.cuisine}</span>}
          {post.location && <span><MapPin size={13} /> {post.location}</span>}
        </p>}
      </div>
      {post.rating && <span className="count-pill" aria-label={`Rated ${post.rating} out of 5`}><Star size={12} /> {post.rating}/5</span>}
    </div>
    <p className="food-post__description">{post.description}</p>
    <footer className="food-post__author">
      <div className="avatar">{post.author.profile_picture ? <img src={post.author.profile_picture} alt="" /> : initial(post.author)}</div>
      <span>{displayName(post.author)} · {formatDate(post.created_at, true)}</span>
    </footer>
  </article>
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
        {posts.map((post) => <FoodPostCard post={post} key={post.id} />)}
      </div> : <div className="empty-state"><span><Utensils size={22} /></span><h3>No posts yet</h3><p>Be the first to recommend a place to eat.</p></div>}
    </section>}
  </>
}
