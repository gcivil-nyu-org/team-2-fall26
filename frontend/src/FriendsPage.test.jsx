import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

import { api as realApi } from './api'
import { FriendsPage } from './FriendsPage'

// #17/#18 AC: a friend request (and a friend) shows the other person's
// profile photo, falling back to an initial when they don't have one —
// same avatar pattern already used for your own picture in the sidebar.
// The <img> is decorative (alt=""), so it has no accessible "img" role —
// same reason App.test.jsx reaches it via querySelector rather than
// getByRole('img').

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
    friends: [],
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

describe('profile photos on friend requests and the friends list', () => {
  test('a received request shows the sender’s photo when they have one', async () => {
    mockFriendsLoad(friendsPayload({
      received_requests: [{ id: 1, direction: 'received', user: { id: 2, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu', profile_picture: '/media/profile-pictures/sam.png' } }],
    }))
    render(<FriendsPage />)
    await screen.findByText('Sam Lee')
    expect(rowFor('Sam Lee').querySelector('img')).toHaveAttribute('src', '/media/profile-pictures/sam.png')
  })

  test('a received request falls back to an initial when the sender has no photo', async () => {
    mockFriendsLoad(friendsPayload({
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
      friends: [{ id: 3, first_name: 'Jordan', last_name: '', email: 'jordan@nyu.edu', profile_picture: '/media/profile-pictures/jordan.png' }],
    }))
    render(<FriendsPage />)
    await screen.findByText('Jordan')
    expect(rowFor('Jordan').querySelector('img')).toHaveAttribute('src', '/media/profile-pictures/jordan.png')
  })

  test('a friend with no photo still falls back to an initial', async () => {
    mockFriendsLoad(friendsPayload({
      friends: [{ id: 3, first_name: 'Jordan', last_name: '', email: 'jordan@nyu.edu', profile_picture: null }],
    }))
    render(<FriendsPage />)
    await screen.findByText('Jordan')
    const row = rowFor('Jordan')
    expect(row.querySelector('img')).toBeNull()
    expect(row.querySelector('.avatar')).toHaveTextContent('J')
  })
})
