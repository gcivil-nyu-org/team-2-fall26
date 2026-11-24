import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { api as realApi } from './api'
import { ConversationPage, MessagesPage } from './MessagesPage'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, api: vi.fn() }
})

afterEach(() => {
  cleanup()
  vi.mocked(realApi).mockReset()
})

const sam = { id: 2, email: 'sam@nyu.edu', first_name: 'Sam', last_name: 'Lee', profile_picture: null }

function renderInbox() {
  return render(<MemoryRouter><MessagesPage /></MemoryRouter>)
}

function renderThread(id = 2) {
  return render(<MemoryRouter initialEntries={[`/messages/${id}`]}>
    <Routes><Route path="/messages/:userId" element={<ConversationPage />} /></Routes>
  </MemoryRouter>)
}

describe('unread counts and read tracking (#37)', () => {
  test('a friend who has written shows how many messages are unread', async () => {
    vi.mocked(realApi).mockResolvedValue({ friends: [{ ...sam, unread_messages: 3 }, { ...sam, id: 3, first_name: 'Kim', unread_messages: 0 }] })
    renderInbox()
    expect(await screen.findByRole('link', { name: /open conversation with sam lee/i })).toHaveTextContent('3')
    expect(screen.getByLabelText('3 unread')).toBeInTheDocument()
    expect(screen.getAllByLabelText(/unread$/)).toHaveLength(1)
  })

  test('no count appears when nothing is unread or the server sends none', async () => {
    vi.mocked(realApi).mockResolvedValue({ friends: [{ ...sam, unread_messages: 0 }, { ...sam, id: 3, first_name: 'Kim' }] })
    renderInbox()
    await screen.findByRole('link', { name: /open conversation with sam lee/i })
    expect(screen.queryByLabelText(/unread$/)).toBeNull()
  })

  test('opening a conversation tells the sidebar to refresh its counts', async () => {
    const heard = vi.fn()
    window.addEventListener('semesterpilot:alerts-changed', heard)
    vi.mocked(realApi).mockResolvedValue({ friend: sam, messages: [] })
    renderThread()
    await screen.findByText('No messages yet')
    window.removeEventListener('semesterpilot:alerts-changed', heard)
    expect(heard).toHaveBeenCalledTimes(1)
  })

  test('a conversation that fails to load does not announce a change', async () => {
    const heard = vi.fn()
    window.addEventListener('semesterpilot:alerts-changed', heard)
    vi.mocked(realApi).mockRejectedValue(new Error('Network down'))
    renderThread()
    await screen.findByRole('alert')
    window.removeEventListener('semesterpilot:alerts-changed', heard)
    expect(heard).not.toHaveBeenCalled()
  })
})

describe('conversation list (#21)', () => {
  test('links to existing friends and not to requests', async () => {
    vi.mocked(realApi).mockResolvedValue({ friends: [sam], received_requests: [{ user: { id: 9, email: 'not-friend@nyu.edu' } }], sent_requests: [] })
    renderInbox()
    expect(await screen.findByRole('link', { name: /open conversation with sam lee/i })).toHaveAttribute('href', '/messages/2')
    expect(screen.queryByText('not-friend@nyu.edu')).not.toBeInTheDocument()
  })

  test('shows useful empty state without friends', async () => {
    vi.mocked(realApi).mockResolvedValue({ friends: [], received_requests: [], sent_requests: [] })
    renderInbox()
    expect(await screen.findByText('No conversations yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Find friends' })).toHaveAttribute('href', '/friends')
  })

  test('shows load errors and offers retry', async () => {
    vi.mocked(realApi).mockRejectedValueOnce(new Error('Network down')).mockResolvedValue({ friends: [sam] })
    renderInbox()
    expect(await screen.findByRole('alert')).toHaveTextContent('Network down')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Sam Lee')).toBeInTheDocument()
  })
})

describe('conversation history and sending (#20, #21)', () => {
  test('renders messages in the order returned with sender and timestamps', async () => {
    vi.mocked(realApi).mockResolvedValue({
      friend: sam,
      messages: [
        { id: 1, sender_name: 'Sam Lee', sender_id: 2, body: 'Hello', is_mine: false, created_at: '2026-11-04T15:00:00Z' },
        { id: 2, sender_name: 'Alex', sender_id: 1, body: 'Hi back', is_mine: true, created_at: '2026-11-04T15:01:00Z' },
      ],
    })
    renderThread()
    await screen.findByText('Hello')
    const rows = document.querySelectorAll('.conversation__message')
    expect(Array.from(rows, (row) => row.querySelector('p').textContent)).toEqual(['Hello', 'Hi back'])
    expect(rows[0]).toHaveTextContent('Sam Lee')
    expect(rows[1]).toHaveTextContent('You')
    expect(rows[0].querySelector('time')).toHaveAttribute('datetime', '2026-11-04T15:00:00Z')
  })

  test('empty conversation encourages first message', async () => {
    vi.mocked(realApi).mockResolvedValue({ friend: sam, messages: [] })
    renderThread()
    expect(await screen.findByText('No messages yet')).toBeInTheDocument()
  })

  test('sends a trimmed non-empty message and shows it immediately', async () => {
    const mock = vi.mocked(realApi)
    mock.mockImplementation(async (path, opts) => {
      if (opts?.method === 'POST') {
        expect(path).toBe('/social/messages/2/')
        expect(opts.body).toEqual({ body: 'Hello!' })
        return { message: { id: 1, body: 'Hello!', is_mine: true, sender_name: 'Alex', created_at: '2026-11-04T15:00:00Z' } }
      }
      return { friend: sam, messages: [] }
    })
    renderThread()
    await screen.findByText('No messages yet')
    const user = userEvent.setup()
    const input = screen.getByLabelText('Your message')
    await user.type(input, '  Hello!  ')
    await user.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('Hello!')).toBeInTheDocument()
    expect(input).toHaveValue('')
  })

  test('cannot submit whitespace-only text', async () => {
    vi.mocked(realApi).mockResolvedValue({ friend: sam, messages: [] })
    renderThread()
    await screen.findByText('No messages yet')
    await userEvent.type(screen.getByLabelText('Your message'), '   ')
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()
    expect(realApi).toHaveBeenCalledTimes(1)
  })

  test('keeps draft and displays server validation errors', async () => {
    const failure = new Error('Invalid message')
    failure.errors = { body: ['Message is too long.'] }
    vi.mocked(realApi).mockResolvedValueOnce({ friend: sam, messages: [] }).mockRejectedValueOnce(failure)
    renderThread()
    await screen.findByText('No messages yet')
    await userEvent.type(screen.getByLabelText('Your message'), 'Hello')
    await userEvent.click(screen.getByRole('button', { name: 'Send message' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Message is too long.')
    expect(screen.getByLabelText('Your message')).toHaveValue('Hello')
  })

  test('rejects stale or non-friend conversation links', async () => {
    const error = new Error('Not found')
    error.status = 404
    vi.mocked(realApi).mockRejectedValue(error)
    renderThread(999)
    expect(await screen.findByRole('alert')).toHaveTextContent(/only message current friends/i)
    expect(screen.queryByLabelText('Your message')).not.toBeInTheDocument()
  })
})

// #31: a friend who hides their email must not have it shown in chat screens.
describe('friends who hide their email (#31)', () => {
  const hiddenSam = { ...sam, email: null }

  test('the conversation list shows the name without an email line', async () => {
    vi.mocked(realApi).mockResolvedValue({ friends: [hiddenSam], received_requests: [], sent_requests: [] })
    renderInbox()
    const link = await screen.findByRole('link', { name: /open conversation with sam lee/i })
    expect(link.querySelector('small')).toBeNull()
  })

  test('the conversation header shows the name without an email subtitle', async () => {
    vi.mocked(realApi).mockResolvedValue({ friend: hiddenSam, messages: [] })
    renderThread()
    expect(await screen.findByRole('heading', { name: 'Sam Lee' })).toBeInTheDocument()
    expect(document.querySelector('.page-header__subtitle')).toBeNull()
  })
})

describe('shared food posts in a conversation (#22)', () => {
  const sharedPost = {
    available: true, id: 7, place_name: "Joe's Pizza", description: 'Grab a plain slice.', location: '7 Carmine St',
    cuisine: 'Pizza', rating: 5, created_at: '2026-11-03T18:00:00Z',
    author: { id: 3, email: 'jordan@nyu.edu', first_name: 'Jordan', last_name: '', profile_picture: null },
  }

  function renderThreadWithPost(messages) {
    vi.mocked(realApi).mockResolvedValue({ friend: sam, messages })
    return render(<MemoryRouter initialEntries={['/messages/2']}>
      <Routes>
        <Route path="/messages/:userId" element={<ConversationPage />} />
        <Route path="/community/posts/:postId" element={<h1>Post page</h1>} />
      </Routes>
    </MemoryRouter>)
  }

  test('shows the shared post with its content, author and the note', async () => {
    renderThreadWithPost([{ id: 1, sender_name: 'Sam Lee', body: 'You have to try this', is_mine: false, created_at: '2026-11-04T15:00:00Z', shared_post: sharedPost }])
    const card = await screen.findByRole('link', { name: "Open shared post: Joe's Pizza" })
    expect(card).toHaveAttribute('href', '/community/posts/7')
    expect(card).toHaveTextContent('Grab a plain slice.')
    expect(card).toHaveTextContent('Pizza')
    expect(card).toHaveTextContent('7 Carmine St')
    expect(card).toHaveTextContent('5/5')
    expect(card).toHaveTextContent('Posted by Jordan')
    expect(screen.getByText('You have to try this')).toBeInTheDocument()
  })

  test('opening the shared post goes to its page', async () => {
    renderThreadWithPost([{ id: 1, sender_name: 'Sam Lee', body: '', is_mine: false, created_at: '2026-11-04T15:00:00Z', shared_post: sharedPost }])
    await userEvent.click(await screen.findByRole('link', { name: "Open shared post: Joe's Pizza" }))
    expect(await screen.findByRole('heading', { name: 'Post page' })).toBeInTheDocument()
  })

  test('a long description is shortened in the conversation', async () => {
    const description = `${'Great falafel. '.repeat(20)}The end.`
    renderThreadWithPost([{ id: 1, sender_name: 'Sam Lee', body: '', is_mine: false, created_at: '2026-11-04T15:00:00Z', shared_post: { ...sharedPost, description } }])
    const card = await screen.findByRole('link', { name: "Open shared post: Joe's Pizza" })
    expect(card).toHaveTextContent('…')
    expect(card).not.toHaveTextContent('The end.')
  })

  test('a removed post says it is no longer available', async () => {
    renderThreadWithPost([{ id: 1, sender_name: 'Sam Lee', body: 'Try this', is_mine: false, created_at: '2026-11-04T15:00:00Z', shared_post: { available: false } }])
    expect(await screen.findByText('This post is no longer available.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Open shared post/ })).not.toBeInTheDocument()
    expect(screen.getByText('Try this')).toBeInTheDocument()
  })
})
