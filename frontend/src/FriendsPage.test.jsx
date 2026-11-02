import assert from 'node:assert/strict'
import test from 'node:test'

import '../test/dom-setup.mjs'

import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { FriendsPage } from './FriendsPage.jsx'

// Covers the "remove a friend" confirm/cancel/removal flow (#19 AC: confirm
// before removing, cancel leaves the friendship untouched, confirming
// removes it and it disappears from the list, and a failed removal doesn't
// silently drop the friend).

function friendsPayload(overrides = {}) {
  return {
    received_requests: [],
    sent_requests: [],
    friends: [{ id: 1, friendship_id: 42, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu' }],
    ...overrides,
  }
}

function jsonResponse(body, { ok = true, status = ok ? 200 : 400 } = {}) {
  return { ok, status, json: async () => body }
}

test.afterEach(() => {
  cleanup()
  delete globalThis.fetch
})

test('remove button asks for confirmation before anything happens', async () => {
  globalThis.fetch = async (url) => {
    assert.equal(url, '/api/social/friends/')
    return jsonResponse(friendsPayload())
  }
  render(<FriendsPage />)
  await screen.findByText('Sam Lee')

  assert.equal(screen.queryByText('Remove Sam Lee as a friend?'), null)
  fireEvent.click(screen.getByRole('button', { name: /remove sam lee as a friend/i }))
  assert.ok(screen.getByText('Remove Sam Lee as a friend?'))
})

test('canceling the confirmation leaves the friendship unchanged', async () => {
  let deleteWasCalled = false
  globalThis.fetch = async (url, options) => {
    if (options?.method === 'DELETE') { deleteWasCalled = true }
    return jsonResponse(friendsPayload())
  }
  render(<FriendsPage />)
  await screen.findByText('Sam Lee')

  fireEvent.click(screen.getByRole('button', { name: /remove sam lee as a friend/i }))
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

  assert.equal(deleteWasCalled, false)
  assert.equal(screen.queryByText('Remove Sam Lee as a friend?'), null)
  assert.ok(screen.getByText('Sam Lee'), 'the friend is still listed after canceling')
})

test('confirming sends the DELETE request and the friend disappears from the list', async () => {
  let friendsRequestCount = 0
  let deleteUrl = null
  globalThis.fetch = async (url, options) => {
    if (url === '/api/social/friends/') {
      friendsRequestCount += 1
      return jsonResponse(friendsRequestCount === 1 ? friendsPayload() : friendsPayload({ friends: [] }))
    }
    if (options?.method === 'DELETE') {
      deleteUrl = url
      return jsonResponse({ ok: true })
    }
    throw new Error(`unexpected fetch: ${url}`)
  }
  render(<FriendsPage />)
  await screen.findByText('Sam Lee')

  fireEvent.click(screen.getByRole('button', { name: /remove sam lee as a friend/i }))
  fireEvent.click(screen.getByRole('button', { name: 'Remove' }))

  await screen.findByText('No friends yet')
  assert.equal(deleteUrl, '/api/social/friends/requests/42/')
})

test('a failed removal shows an error and keeps the friend in the list', async () => {
  globalThis.fetch = async (url, options) => {
    if (url === '/api/social/friends/') return jsonResponse(friendsPayload())
    if (options?.method === 'DELETE') return jsonResponse({ detail: 'Something went wrong.' }, { ok: false, status: 500 })
    throw new Error(`unexpected fetch: ${url}`)
  }
  render(<FriendsPage />)
  await screen.findByText('Sam Lee')

  fireEvent.click(screen.getByRole('button', { name: /remove sam lee as a friend/i }))
  fireEvent.click(screen.getByRole('button', { name: 'Remove' }))

  await screen.findByText('Something went wrong.')
  assert.ok(screen.getByText('Sam Lee'), 'the friend is still listed after a failed removal')
})
