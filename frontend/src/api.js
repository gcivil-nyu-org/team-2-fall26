function cookie(name) {
  return document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${name}=`))
    ?.split('=')
    .slice(1)
    .join('=')
}

export async function api(path, options = {}) {
  const method = options.method || 'GET'
  const headers = { Accept: 'application/json', ...options.headers }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    headers['X-CSRFToken'] = decodeURIComponent(cookie('csrftoken') || '')
  }
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    ...options,
    method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(data.detail || 'Something went wrong.')
    error.status = response.status
    error.errors = data.errors || {}
    throw error
  }
  return data
}

export function toUTCInput(iso) {
  if (!iso) return ''
  // Django interprets datetime-local values in UTC. Keep the input in that
  // same zone so opening and saving a form cannot shift the deadline.
  return new Date(iso).toISOString().slice(0, 16)
}

export function formatDate(iso, includeYear = false) {
  if (!iso) return 'No deadline'
  const date = new Date(iso)
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'UTC',
    timeZoneName: 'short',
    month: 'short',
    day: 'numeric',
    ...(includeYear ? { year: 'numeric' } : {}),
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}
