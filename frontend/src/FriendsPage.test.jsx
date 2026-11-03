import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { api as realApi } from './api'
import { FriendsPage } from './FriendsPage'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, api: vi.fn() }
})

afterEach(() => {
  cleanup()
  vi.mocked(realApi).mockReset()
})

function friendsPayload(overrides = {}) {
  return {
    received_requests: [],
    sent_requests: [],
    friends: [{ id: 1, friendship_id: 42, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu' }],
    ...overrides,
  }
}

function mockFriendsLoad(payload) {
  vi.mocked(realApi).mockImplementation(async (path) => {
    if (path === '/social/friends/') return payload
    throw new Error(`unexpected call to api(${path})`)
  })
}

function rowFor(text) {
  return screen.getByText(text).closest('.friend-row')
}

// Covers the "remove a friend" confirm/cancel/removal flow (#19 AC: confirm
// before removing, cancel leaves the friendship untouched, confirming
// removes it and it disappears from the list, and a failed removal doesn't
// silently drop the friend).
describe('removing a friend', () => {
  test('the remove button asks for confirmation before anything happens', async () => {
    mockFriendsLoad(friendsPayload())
    render(<FriendsPage />)
    await screen.findByText('Sam Lee')

    expect(screen.queryByText('Remove Sam Lee as a friend?')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /remove sam lee as a friend/i }))
    expect(screen.getByText('Remove Sam Lee as a friend?')).toBeInTheDocument()
  })

  test('canceling the confirmation leaves the friendship unchanged', async () => {
    mockFriendsLoad(friendsPayload())
    render(<FriendsPage />)
    await screen.findByText('Sam Lee')

    await userEvent.click(screen.getByRole('button', { name: /remove sam lee as a friend/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(vi.mocked(realApi)).not.toHaveBeenCalledWith(expect.stringContaining('/requests/'), expect.objectContaining({ method: 'DELETE' }))
    expect(screen.queryByText('Remove Sam Lee as a friend?')).not.toBeInTheDocument()
    expect(screen.getByText('Sam Lee')).toBeInTheDocument()
  })

  test('confirming sends the DELETE request and the friend disappears from the list', async () => {
    let friendsRequestCount = 0
    vi.mocked(realApi).mockImplementation(async (path, options) => {
      if (path === '/social/friends/') {
        friendsRequestCount += 1
        return friendsRequestCount === 1 ? friendsPayload() : friendsPayload({ friends: [] })
      }
      if (path === '/social/friends/requests/42/' && options?.method === 'DELETE') return { ok: true }
      throw new Error(`unexpected call to api(${path})`)
    })
    render(<FriendsPage />)
    await screen.findByText('Sam Lee')

    await userEvent.click(screen.getByRole('button', { name: /remove sam lee as a friend/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))

    await waitFor(() => expect(screen.getByText('No friends yet')).toBeInTheDocument())
  })

  test('a failed removal shows an error and keeps the friend in the list', async () => {
    vi.mocked(realApi).mockImplementation(async (path, options) => {
      if (path === '/social/friends/') return friendsPayload()
      if (path === '/social/friends/requests/42/' && options?.method === 'DELETE') {
        throw new Error('Something went wrong.')
      }
      throw new Error(`unexpected call to api(${path})`)
    })
    render(<FriendsPage />)
    await screen.findByText('Sam Lee')

    await userEvent.click(screen.getByRole('button', { name: /remove sam lee as a friend/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))

    await waitFor(() => expect(screen.getByText('Something went wrong.')).toBeInTheDocument())
    expect(screen.getByText('Sam Lee')).toBeInTheDocument()
  })
})

// #17/#18 AC: a friend request (and a friend) shows the other person's
// profile photo, falling back to an initial when they don't have one —
// same avatar pattern already used for your own picture in the sidebar.
// The <img> is decorative (alt=""), so it has no accessible "img" role —
// same reason App.test.jsx reaches it via querySelector rather than
// getByRole('img').
describe('profile photos on friend requests and the friends list', () => {
  test('a received request shows the sender’s photo when they have one', async () => {
    mockFriendsLoad(friendsPayload({
      friends: [],
      received_requests: [{ id: 1, direction: 'received', user: { id: 2, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu', profile_picture: '/media/profile-pictures/sam.png' } }],
    }))
    render(<FriendsPage />)
    await screen.findByText('Sam Lee')
    expect(rowFor('Sam Lee').querySelector('img')).toHaveAttribute('src', '/media/profile-pictures/sam.png')
  })

  test('a received request falls back to an initial when the sender has no photo', async () => {
    mockFriendsLoad(friendsPayload({
      friends: [],
      received_requests: [{ id: 1, direction: 'received', user: { id: 2, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu', profile_picture: null } }],
    }))
    render(<FriendsPage />)
    await screen.findByText('Sam Lee')
    const row = rowFor('Sam Lee')
    expect(row.querySelector('img')).toBeNull()
    expect(row.querySelector('.avatar')).toHaveTextContent('S')
  })

  test('a friend in "Your friends" shows their photo when they have one', async () => {
    mockFriendsLoad(friendsPayload({
      friends: [{ id: 3, friendship_id: 42, first_name: 'Jordan', last_name: '', email: 'jordan@nyu.edu', profile_picture: '/media/profile-pictures/jordan.png' }],
    }))
    render(<FriendsPage />)
    await screen.findByText('Jordan')
    expect(rowFor('Jordan').querySelector('img')).toHaveAttribute('src', '/media/profile-pictures/jordan.png')
  })

  test('a friend with no photo still falls back to an initial', async () => {
    mockFriendsLoad(friendsPayload({
      friends: [{ id: 3, friendship_id: 42, first_name: 'Jordan', last_name: '', email: 'jordan@nyu.edu', profile_picture: null }],
    }))
    render(<FriendsPage />)
    await screen.findByText('Jordan')
    const row = rowFor('Jordan')
    expect(row.querySelector('img')).toBeNull()
    expect(row.querySelector('.avatar')).toHaveTextContent('J')
  })
})
