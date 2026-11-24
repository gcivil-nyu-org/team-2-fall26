import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useNavigate } from 'react-router-dom'

import { api as realApi } from './api'
import { ALERTS_REFRESH_MS, badgeText, refreshAlerts } from './alerts'
import { AppShell, AuthContext } from './App'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, api: vi.fn() }
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.mocked(realApi).mockReset()
})

const authValue = {
  session: { loading: false, authenticated: true, user: { first_name: 'Sanchu', email: 'sanchu@nyu.edu', profile_picture: null } },
  refresh: vi.fn(),
  setSession: vi.fn(),
}

function Jump() {
  const navigate = useNavigate()
  return <button onClick={() => navigate('/messages')}>go to messages</button>
}

function renderShell() {
  return render(<MemoryRouter><AuthContext.Provider value={authValue}><AppShell><Jump /></AppShell></AuthContext.Provider></MemoryRouter>)
}

function mockAlerts(first, ...rest) {
  const mock = vi.mocked(realApi)
  mock.mockResolvedValueOnce(first)
  rest.forEach((next) => mock.mockResolvedValueOnce(next))
  mock.mockResolvedValue(rest.at(-1) ?? first)
}

// #37: counts on Friends and Messages in the sidebar.
describe('sidebar alert badges', () => {
  test('asks for the counts once the shell loads', async () => {
    mockAlerts({ friend_requests: 0, unread_messages: 0 })
    renderShell()
    await screen.findByRole('link', { name: 'Friends' })
    expect(realApi).toHaveBeenCalledWith('/social/alerts/')
  })

  test('shows a badge for pending friend requests and for unread messages', async () => {
    mockAlerts({ friend_requests: 2, unread_messages: 5 })
    renderShell()
    expect(await screen.findByRole('link', { name: /friends.*2 pending friend requests/i })).toHaveTextContent('2')
    expect(screen.getByRole('link', { name: /messages.*5 unread messages/i })).toHaveTextContent('5')
  })

  test('shows no badge when there is nothing new', async () => {
    mockAlerts({ friend_requests: 0, unread_messages: 0 })
    renderShell()
    await screen.findByRole('link', { name: 'Friends' })
    expect(screen.getByRole('link', { name: 'Messages' })).toBeInTheDocument()
    expect(document.querySelector('.nav-badge')).toBeNull()
  })

  test('only the matching link gets a badge', async () => {
    mockAlerts({ friend_requests: 0, unread_messages: 3 })
    renderShell()
    await screen.findByRole('link', { name: /messages.*3 unread messages/i })
    expect(screen.getByRole('link', { name: 'Friends' })).toBeInTheDocument()
    expect(document.querySelectorAll('.nav-badge')).toHaveLength(1)
  })

  test('large counts are capped', async () => {
    mockAlerts({ friend_requests: 0, unread_messages: 140 })
    renderShell()
    expect(await screen.findByRole('link', { name: /messages/i })).toHaveTextContent('99+')
    expect(badgeText(99)).toBe('99')
    expect(badgeText(100)).toBe('99+')
  })

  test('a failed request leaves the shell working with no badges', async () => {
    vi.mocked(realApi).mockRejectedValue(new Error('Network down'))
    renderShell()
    expect(await screen.findByRole('link', { name: 'Friends' })).toBeInTheDocument()
    expect(document.querySelector('.nav-badge')).toBeNull()
  })

  test('a failed refresh keeps the badges it already had', async () => {
    mockAlerts({ friend_requests: 0, unread_messages: 4 })
    renderShell()
    await screen.findByRole('link', { name: /messages.*4 unread/i })
    vi.mocked(realApi).mockRejectedValue(new Error('Network down'))
    await act(async () => { refreshAlerts() })
    expect(screen.getByRole('link', { name: /messages.*4 unread/i })).toBeInTheDocument()
  })

  test('junk in the response does not break the badges', async () => {
    mockAlerts({ friend_requests: 'lots', unread_messages: null })
    renderShell()
    await screen.findByRole('link', { name: 'Friends' })
    expect(document.querySelector('.nav-badge')).toBeNull()
  })

  test('refreshes when a page announces a change', async () => {
    mockAlerts({ friend_requests: 0, unread_messages: 2 }, { friend_requests: 0, unread_messages: 0 })
    renderShell()
    await screen.findByRole('link', { name: /messages.*2 unread/i })
    await act(async () => { refreshAlerts() })
    expect(screen.getByRole('link', { name: 'Messages' })).toBeInTheDocument()
    expect(document.querySelector('.nav-badge')).toBeNull()
  })

  test('refreshes when the student moves to another page', async () => {
    const user = userEvent.setup()
    mockAlerts({ friend_requests: 1, unread_messages: 0 }, { friend_requests: 0, unread_messages: 0 })
    renderShell()
    await screen.findByRole('link', { name: /friends.*1 pending/i })
    await user.click(screen.getByRole('button', { name: 'go to messages' }))
    expect(await screen.findByRole('link', { name: 'Friends' })).toBeInTheDocument()
    expect(realApi).toHaveBeenCalledTimes(2)
  })

  test('keeps itself current every 30 seconds while the app stays open', async () => {
    vi.useFakeTimers()
    mockAlerts({ friend_requests: 0, unread_messages: 0 }, { friend_requests: 3, unread_messages: 0 })
    renderShell()
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(document.querySelector('.nav-badge')).toBeNull()
    await act(async () => { await vi.advanceTimersByTimeAsync(ALERTS_REFRESH_MS) })
    expect(screen.getByRole('link', { name: /friends.*3 pending/i })).toBeInTheDocument()
  })

  test('refreshes when the student comes back to the tab', async () => {
    mockAlerts({ friend_requests: 0, unread_messages: 0 }, { friend_requests: 4, unread_messages: 0 })
    renderShell()
    await screen.findByRole('link', { name: 'Friends' })
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')) })
    expect(await screen.findByRole('link', { name: /friends.*4 pending/i })).toBeInTheDocument()
  })

  test('does not refresh while the tab is hidden', async () => {
    mockAlerts({ friend_requests: 0, unread_messages: 0 })
    renderShell()
    await screen.findByRole('link', { name: 'Friends' })
    const calls = vi.mocked(realApi).mock.calls.length
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')) })
    visibility.mockRestore()
    expect(vi.mocked(realApi).mock.calls.length).toBe(calls)
  })

  test('stops listening and polling when the shell goes away', async () => {
    vi.useFakeTimers()
    mockAlerts({ friend_requests: 0, unread_messages: 0 })
    const { unmount } = renderShell()
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    unmount()
    const calls = vi.mocked(realApi).mock.calls.length
    refreshAlerts()
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(ALERTS_REFRESH_MS * 2)
    expect(vi.mocked(realApi).mock.calls.length).toBe(calls)
  })
})

describe('refresh timing', () => {
  test('polls at least every 30 seconds', () => {
    expect(ALERTS_REFRESH_MS).toBeLessThanOrEqual(30_000)
  })
})

describe('refreshAlerts', () => {
  beforeEach(() => vi.useRealTimers())

  test('tells every listener the counts changed', () => {
    const heard = vi.fn()
    window.addEventListener('semesterpilot:alerts-changed', heard)
    refreshAlerts()
    window.removeEventListener('semesterpilot:alerts-changed', heard)
    expect(heard).toHaveBeenCalledTimes(1)
  })
})
