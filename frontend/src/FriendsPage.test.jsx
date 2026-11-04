import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { api as realApi } from './api'
import { FriendProfilePage, FriendsPage } from './FriendsPage'

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

// FriendRow links to a friend's profile now (#18), so every render needs a
// Router around it — a bare <FriendsPage /> throws without one.
function renderFriendsPage() {
  return render(<MemoryRouter><FriendsPage /></MemoryRouter>)
}

// #18 AC: "I can open a friends list that shows all students I am
// currently connected with" / "each friend displays their full name,
// username, and profile photo" (see README's note on #16/#17/#18 — there's
// no real username field in this app, so name + email are what's shown and
// tested) / "if I do not have any friends yet, the system displays a
// message indicating that my friends list is empty."
describe('viewing the friends list', () => {
  test('shows every connected friend\'s name and email', async () => {
    mockFriendsLoad(friendsPayload({
      friends: [
        { id: 1, friendship_id: 42, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu' },
        { id: 2, friendship_id: 43, first_name: 'Jordan', last_name: 'Diaz', email: 'jordan@nyu.edu' },
      ],
    }))
    renderFriendsPage()
    await screen.findByText('Sam Lee')
    expect(screen.getByText('sam@nyu.edu')).toBeInTheDocument()
    expect(screen.getByText('Jordan Diaz')).toBeInTheDocument()
    expect(screen.getByText('jordan@nyu.edu')).toBeInTheDocument()
  })

  test('shows a message when there are no friends yet', async () => {
    mockFriendsLoad(friendsPayload({ friends: [] }))
    renderFriendsPage()
    expect(await screen.findByText('No friends yet')).toBeInTheDocument()
    expect(screen.getByText(/get started/i)).toBeInTheDocument()
  })
})

  test('shows an error with a retry option when the list fails to load', async () => {
    let callCount = 0
    vi.mocked(realApi).mockImplementation(async (path) => {
      if (path === '/social/friends/') {
        callCount += 1
        if (callCount === 1) throw new Error('Could not load your friends.')
        return friendsPayload({ friends: [] })
      }
      throw new Error(`unexpected call to api(${path})`)
    })
    renderFriendsPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load your friends.')
    await userEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(await screen.findByText('No friends yet')).toBeInTheDocument()
  })

// Covers the "remove a friend" confirm/cancel/removal flow (#19 AC: confirm
// before removing, cancel leaves the friendship untouched, confirming
// removes it and it disappears from the list, and a failed removal doesn't
// silently drop the friend).
describe('removing a friend', () => {
  test('the remove button asks for confirmation before anything happens', async () => {
    mockFriendsLoad(friendsPayload())
    renderFriendsPage()
    await screen.findByText('Sam Lee')

    expect(screen.queryByText('Remove Sam Lee as a friend?')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /remove sam lee as a friend/i }))
    expect(screen.getByText('Remove Sam Lee as a friend?')).toBeInTheDocument()
  })

  test('canceling the confirmation leaves the friendship unchanged', async () => {
    mockFriendsLoad(friendsPayload())
    renderFriendsPage()
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
    renderFriendsPage()
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
    renderFriendsPage()
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
    renderFriendsPage()
    await screen.findByText('Sam Lee')
    expect(rowFor('Sam Lee').querySelector('img')).toHaveAttribute('src', '/media/profile-pictures/sam.png')
  })

  test('a received request falls back to an initial when the sender has no photo', async () => {
    mockFriendsLoad(friendsPayload({
      friends: [],
      received_requests: [{ id: 1, direction: 'received', user: { id: 2, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu', profile_picture: null } }],
    }))
    renderFriendsPage()
    await screen.findByText('Sam Lee')
    const row = rowFor('Sam Lee')
    expect(row.querySelector('img')).toBeNull()
    expect(row.querySelector('.avatar')).toHaveTextContent('S')
  })

  test('a friend in "Your friends" shows their photo when they have one', async () => {
    mockFriendsLoad(friendsPayload({
      friends: [{ id: 3, friendship_id: 42, first_name: 'Jordan', last_name: '', email: 'jordan@nyu.edu', profile_picture: '/media/profile-pictures/jordan.png' }],
    }))
    renderFriendsPage()
    await screen.findByText('Jordan')
    expect(rowFor('Jordan').querySelector('img')).toHaveAttribute('src', '/media/profile-pictures/jordan.png')
  })

  test('a friend with no photo still falls back to an initial', async () => {
    mockFriendsLoad(friendsPayload({
      friends: [{ id: 3, friendship_id: 42, first_name: 'Jordan', last_name: '', email: 'jordan@nyu.edu', profile_picture: null }],
    }))
    renderFriendsPage()
    await screen.findByText('Jordan')
    const row = rowFor('Jordan')
    expect(row.querySelector('img')).toBeNull()
    expect(row.querySelector('.avatar')).toHaveTextContent('J')
  })
})

// #18 AC: "I can select a friend from the list to view their profile."
describe('selecting a friend to view their profile', () => {
  test('a friend row links to their profile by friendship id', async () => {
    mockFriendsLoad(friendsPayload())
    renderFriendsPage()
    await screen.findByText('Sam Lee')
    expect(screen.getByRole('link', { name: /view sam lee.s profile/i })).toHaveAttribute('href', '/friends/42')
  })

  test('the profile page shows the friend’s name, email, and photo', async () => {
    vi.mocked(realApi).mockImplementation(async (path) => {
      if (path === '/social/friends/42/') {
        return { user: { id: 2, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu', profile_picture: '/media/profile-pictures/sam.png' } }
      }
      throw new Error(`unexpected call to api(${path})`)
    })
    render(
      <MemoryRouter initialEntries={['/friends/42']}>
        <Routes><Route path="/friends/:friendshipId" element={<FriendProfilePage />} /></Routes>
      </MemoryRouter>,
    )
    await screen.findByText('Sam Lee')
    expect(screen.getByText('sam@nyu.edu')).toBeInTheDocument()
    expect(document.querySelector('.friend-profile img')).toHaveAttribute('src', '/media/profile-pictures/sam.png')
    expect(screen.getByRole('link', { name: /back to friends/i })).toHaveAttribute('href', '/friends')
  })

  test('a friend with no photo shows an initial on their profile page too', async () => {
    vi.mocked(realApi).mockImplementation(async (path) => {
      if (path === '/social/friends/42/') {
        return { user: { id: 2, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu', profile_picture: null } }
      }
      throw new Error(`unexpected call to api(${path})`)
    })
    render(
      <MemoryRouter initialEntries={['/friends/42']}>
        <Routes><Route path="/friends/:friendshipId" element={<FriendProfilePage />} /></Routes>
      </MemoryRouter>,
    )
    await screen.findByText('Sam Lee')
    expect(document.querySelector('.friend-profile img')).toBeNull()
    expect(document.querySelector('.friend-profile .avatar')).toHaveTextContent('S')
  })

  test('a removed or non-existent friendship shows an error instead of a blank page', async () => {
    vi.mocked(realApi).mockImplementation(async (path) => {
      if (path === '/social/friends/999/') {
        const error = new Error('Not found.')
        error.status = 404
        throw error
      }
      throw new Error(`unexpected call to api(${path})`)
    })
    render(
      <MemoryRouter initialEntries={['/friends/999']}>
        <Routes><Route path="/friends/:friendshipId" element={<FriendProfilePage />} /></Routes>
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/couldn.t be found/i))
  })
})


describe('messaging navigation (#20, #21)', () => {
  test('an accepted friend has a Message link using their user id, not the friendship id', async () => {
    mockFriendsLoad(friendsPayload({
      friends: [{ id: 2, friendship_id: 42, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu' }],
    }))
    renderFriendsPage()
    await screen.findByText('Sam Lee')

    expect(screen.getByRole('link', { name: 'Message Sam Lee' })).toHaveAttribute('href', '/messages/2')
    expect(screen.getByRole('link', { name: /view sam lee.s profile/i })).toHaveAttribute('href', '/friends/42')
  })

  test('a friend profile has a Send message link to the same user', async () => {
    vi.mocked(realApi).mockImplementation(async (path) => {
      if (path === '/social/friends/42/') {
        return { user: { id: 2, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu', profile_picture: null } }
      }
      throw new Error(`unexpected call to api(${path})`)
    })

    render(
      <MemoryRouter initialEntries={['/friends/42']}>
        <Routes><Route path="/friends/:friendshipId" element={<FriendProfilePage />} /></Routes>
      </MemoryRouter>,
    )
    await screen.findByText('Sam Lee')
    expect(screen.getByRole('link', { name: 'Send message' })).toHaveAttribute('href', '/messages/2')
  })
})

describe('bios on the Friends page', () => {
  test('shows bios for friends and pending requests, and nothing when a student has none', async () => {
    mockFriendsLoad(friendsPayload({
      friends: [
        { id: 1, friendship_id: 42, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu', bio: 'Sam studies math.' },
        { id: 2, friendship_id: 43, first_name: 'Ana', last_name: '', email: 'ana@nyu.edu', bio: '' },
      ],
      received_requests: [{ id: 7, status: 'pending', direction: 'received', user: { id: 3, first_name: 'Jordan', last_name: '', email: 'jordan@nyu.edu', bio: 'Jordan likes chess.' } }],
    }))
    renderFriendsPage()

    expect(await screen.findByText('Sam studies math.')).toBeInTheDocument()
    expect(screen.getByText('Jordan likes chess.')).toBeInTheDocument()
    expect(document.querySelectorAll('.friend-row__bio')).toHaveLength(2)
  })
})
