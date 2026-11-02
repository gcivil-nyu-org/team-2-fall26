import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { api as realApi } from './api'
import { FriendsPage } from './FriendsPage'

// Covers the "remove a friend" confirm/cancel/removal flow (#19 AC: confirm
// before removing, cancel leaves the friendship untouched, confirming
// removes it and it disappears from the list, and a failed removal doesn't
// silently drop the friend).

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
