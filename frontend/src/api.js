function cookie(name) {
  return document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${name}=`))
    ?.split('=')
    .slice(1)
    .join('=')
}

// Pure request-shaping logic, split out from api() so it can be unit tested
// without needing a real `document`/`fetch` (see api.test.js). A FormData
// body (file uploads) must keep its own multipart content type (with
// boundary) set by the browser — never JSON-encode it or give it a
// Content-Type header ourselves.
export function buildRequestInit(options = {}) {
  const method = options.method || 'GET'
  const isFormData = options.body instanceof FormData
  const headers = { Accept: 'application/json', ...options.headers }
  if (options.body !== undefined && !isFormData) headers['Content-Type'] = 'application/json'
  return {
    method,
    headers,
    needsCsrf: !['GET', 'HEAD', 'OPTIONS'].includes(method),
    body: options.body === undefined ? undefined : (isFormData ? options.body : JSON.stringify(options.body)),
  }
}

export async function api(path, options = {}) {
  const built = buildRequestInit(options)
  if (built.needsCsrf) built.headers['X-CSRFToken'] = decodeURIComponent(cookie('csrftoken') || '')
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    ...options,
    method: built.method,
    headers: built.headers,
    body: built.body,
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
