import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { api as realApi } from './api'
import { FoodFeedPage, FoodPostEditPage, FoodPostPage, PREVIEW_LENGTH, previewText } from './FoodFeedPage'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, api: vi.fn() }
})

afterEach(() => {
  cleanup()
  vi.mocked(realApi).mockReset()
})

const sam = { id: 2, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu', profile_picture: null }
const alex = { id: 1, first_name: 'Alex', last_name: '', email: 'alex@nyu.edu', profile_picture: null }

function post(overrides = {}) {
  return {
    id: 1,
    place_name: "Joe's Pizza",
    description: 'Grab a plain slice.',
    location: '7 Carmine St',
    cuisine: 'Pizza',
    rating: 5,
    author: sam,
    created_at: '2026-11-03T18:00:00+00:00',
    ...overrides,
  }
}

function mockFeed(posts, onCreate) {
  vi.mocked(realApi).mockImplementation(async (path, options = {}) => {
    if (path === '/social/posts/' && !options.method) return { posts }
    if (path === '/social/posts/' && options.method === 'POST' && onCreate) return onCreate(options.body)
    throw new Error(`unexpected call to api(${path})`)
  })
}

function renderFeed() {
  return render(<MemoryRouter><FoodFeedPage /></MemoryRouter>)
}

function renderApp(path) {
  return render(<MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/community" element={<FoodFeedPage />} />
      <Route path="/community/posts/:postId" element={<FoodPostPage />} />
      <Route path="/community/posts/:postId/edit" element={<FoodPostEditPage />} />
    </Routes>
  </MemoryRouter>)
}

function feed() {
  return screen.getByRole('region', { name: 'Food feed' })
}

describe('viewing the food feed', () => {
  test('shows each post with its place, details, rating and author', async () => {
    mockFeed([post()])
    renderFeed()
    const card = await screen.findByRole('article', { name: "Joe's Pizza" })
    expect(within(card).getByText('Grab a plain slice.')).toBeInTheDocument()
    expect(within(card).getByText('Pizza')).toBeInTheDocument()
    expect(within(card).getByText(/7 Carmine St/)).toBeInTheDocument()
    expect(within(card).getByLabelText('Rated 5 out of 5')).toBeInTheDocument()
    expect(within(card).getByText(/Sam Lee/)).toBeInTheDocument()
  })

  test('leaves out optional details a post does not have', async () => {
    mockFeed([post({ location: '', cuisine: '', rating: null })])
    renderFeed()
    const card = await screen.findByRole('article', { name: "Joe's Pizza" })
    expect(within(card).queryByText('Pizza')).not.toBeInTheDocument()
    expect(within(card).queryByLabelText(/out of 5/)).not.toBeInTheDocument()
  })

  test('shows a message when there are no posts yet', async () => {
    mockFeed([])
    renderFeed()
    expect(await screen.findByText('No posts yet')).toBeInTheDocument()
  })

  test('shows an error with a working retry when the feed fails to load', async () => {
    vi.mocked(realApi).mockRejectedValueOnce(new Error('Something went wrong.'))
    renderFeed()
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong.')

    mockFeed([post()])
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('article', { name: "Joe's Pizza" })).toBeInTheDocument()
  })
})

// #46 AC: "I can submit the post and see it appear in the community feed."
describe('creating a food post', () => {
  test('submits the post and shows it at the top of the feed', async () => {
    const onCreate = vi.fn((body) => ({ post: post({ id: 2, ...body, author: alex }) }))
    mockFeed([post()], onCreate)
    renderFeed()
    await screen.findByRole('article', { name: "Joe's Pizza" })

    await userEvent.type(screen.getByLabelText('Restaurant or food place'), "Mamoun's")
    await userEvent.type(screen.getByLabelText('Description or recommendation'), 'Best falafel near campus.')
    await userEvent.type(screen.getByLabelText(/Cuisine/), 'Middle Eastern')
    await userEvent.selectOptions(screen.getByLabelText(/Rating/), '4')
    await userEvent.type(screen.getByLabelText(/Location/), '119 Macdougal St')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    expect(onCreate).toHaveBeenCalledWith({
      place_name: "Mamoun's",
      description: 'Best falafel near campus.',
      cuisine: 'Middle Eastern',
      rating: 4,
      location: '119 Macdougal St',
    })
    await screen.findByRole('article', { name: "Mamoun's" })
    const names = within(feed()).getAllByRole('article').map((card) => card.getAttribute('aria-label'))
    expect(names).toEqual(["Mamoun's", "Joe's Pizza"])
    expect(screen.getByRole('status')).toHaveTextContent("Posted your recommendation for Mamoun's.")
    expect(screen.getByLabelText('Restaurant or food place')).toHaveValue('')
    expect(screen.getByLabelText('Description or recommendation')).toHaveValue('')
  })

  test('sends no rating when none is chosen', async () => {
    const onCreate = vi.fn((body) => ({ post: post({ id: 2, ...body }) }))
    mockFeed([], onCreate)
    renderFeed()
    await screen.findByText('No posts yet')

    await userEvent.type(screen.getByLabelText('Restaurant or food place'), 'Somewhere')
    await userEvent.type(screen.getByLabelText('Description or recommendation'), 'Good.')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    await waitFor(() => expect(onCreate).toHaveBeenCalled())
    expect(onCreate.mock.calls[0][0].rating).toBeNull()
  })

  test('shows server validation errors next to the matching fields', async () => {
    mockFeed([])
    renderFeed()
    await screen.findByText('No posts yet')
    vi.mocked(realApi).mockRejectedValueOnce(Object.assign(new Error('Something went wrong.'), {
      status: 400,
      errors: {
        description: ['Add a description or recommendation.'],
        rating: ['Choose a rating from 1 to 5.'],
      },
    }))

    await userEvent.type(screen.getByLabelText('Restaurant or food place'), 'Somewhere')
    await userEvent.type(screen.getByLabelText('Description or recommendation'), ' ')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    const description = await screen.findByText('Add a description or recommendation.')
    expect(description.closest('.field')).toHaveClass('field--error')
    expect(screen.getByText('Choose a rating from 1 to 5.').closest('.field')).toContainElement(screen.getByLabelText(/Rating/))
    expect(screen.getByLabelText('Restaurant or food place')).toHaveValue('Somewhere')
    expect(within(feed()).queryAllByRole('article')).toHaveLength(0)
  })

  test('shows a general error when posting fails without field errors', async () => {
    mockFeed([])
    renderFeed()
    await screen.findByText('No posts yet')
    vi.mocked(realApi).mockRejectedValueOnce(Object.assign(new Error('Authentication required.'), { status: 401, errors: {} }))

    await userEvent.type(screen.getByLabelText('Restaurant or food place'), 'Somewhere')
    await userEvent.type(screen.getByLabelText('Description or recommendation'), 'Good.')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Authentication required.')
  })
})

describe('browsing the food feed', () => {
  test('each place name links to that post', async () => {
    mockFeed([post({ id: 7 })])
    renderFeed()
    const card = await screen.findByRole('article', { name: "Joe's Pizza" })
    expect(within(card).getByRole('link', { name: "Joe's Pizza" })).toHaveAttribute('href', '/community/posts/7')
  })

  test('a long recommendation is shortened with a link to read more', async () => {
    const long = `${'Great falafel. '.repeat(30)}The end.`
    mockFeed([post({ id: 7, description: long })])
    renderFeed()
    const card = await screen.findByRole('article', { name: "Joe's Pizza" })
    expect(within(card).queryByText(/The end\./)).not.toBeInTheDocument()
    expect(within(card).getByText(previewText(long))).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: "Read more about Joe's Pizza" })).toHaveAttribute('href', '/community/posts/7')
  })

  test('a short recommendation is shown in full with no read more link', async () => {
    mockFeed([post()])
    renderFeed()
    const card = await screen.findByRole('article', { name: "Joe's Pizza" })
    expect(within(card).getByText('Grab a plain slice.')).toBeInTheDocument()
    expect(within(card).queryByRole('link', { name: /Read more/ })).not.toBeInTheDocument()
  })

  test('previewText keeps text up to the limit and trims anything longer', () => {
    expect(previewText('a'.repeat(PREVIEW_LENGTH))).toBe('a'.repeat(PREVIEW_LENGTH))
    expect(previewText(`${'a'.repeat(PREVIEW_LENGTH - 1)} b`)).toBe(`${'a'.repeat(PREVIEW_LENGTH - 1)}…`)
  })
})

describe('opening a food post', () => {
  function mockPost(result) {
    vi.mocked(realApi).mockImplementation(async (path, options = {}) => {
      if (path === '/social/posts/' && !options.method) return { posts: [post({ id: 7, description: 'x'.repeat(400) })] }
      if (path === '/social/posts/7/' && !options.method) {
        if (result instanceof Error) throw result
        return { post: result }
      }
      throw new Error(`unexpected call to api(${path})`)
    })
  }

  test('shows the full post, its author and an empty comments section', async () => {
    const long = `${'Great falafel. '.repeat(30)}The end.`
    mockPost(post({ id: 7, description: long }))
    renderApp('/community/posts/7')
    expect(await screen.findByRole('heading', { level: 1, name: "Joe's Pizza" })).toBeInTheDocument()
    const card = screen.getByRole('article', { name: "Joe's Pizza" })
    expect(within(card).getByText(/The end\./)).toBeInTheDocument()
    expect(within(card).getByText('Pizza')).toBeInTheDocument()
    expect(within(card).getByText(/7 Carmine St/)).toBeInTheDocument()
    expect(within(card).getByLabelText('Rated 5 out of 5')).toBeInTheDocument()
    expect(within(card).getByText(/Sam Lee/)).toBeInTheDocument()
    expect(within(card).queryByRole('link', { name: /Read more/ })).not.toBeInTheDocument()
    const comments = screen.getByRole('region', { name: 'Comments' })
    expect(within(comments).getByText('No comments yet')).toBeInTheDocument()
    expect(realApi).toHaveBeenCalledWith('/social/posts/7/')
  })

  test('clicking a post in the feed opens it, and the back link returns', async () => {
    mockPost(post({ id: 7 }))
    renderApp('/community')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('link', { name: "Read more about Joe's Pizza" }))
    expect(await screen.findByRole('heading', { level: 1, name: "Joe's Pizza" })).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: /Back to food feed/ }))
    expect(await screen.findByRole('region', { name: 'Food feed' })).toBeInTheDocument()
  })

  test('a missing or hidden post says it is not available', async () => {
    mockPost(Object.assign(new Error('Post not found.'), { status: 404 }))
    renderApp('/community/posts/7')
    expect(await screen.findByText('This post isn’t available')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Browse the food feed' })).toHaveAttribute('href', '/community')
    expect(screen.queryByRole('region', { name: 'Comments' })).not.toBeInTheDocument()
  })

  test('any other error offers a working retry', async () => {
    mockPost(new Error('Network down.'))
    renderApp('/community/posts/7')
    expect(await screen.findByRole('alert')).toHaveTextContent('Network down.')
    mockPost(post({ id: 7 }))
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { level: 1, name: "Joe's Pizza" })).toBeInTheDocument()
  })
})

// #51/#52: a stand-in server holding one post (id 7). `is_author` is what the
// real API reports for the logged-in student.
function mockOwnPost({ isAuthor = true, onPatch, onDelete } = {}) {
  let current = post({ id: 7, author: isAuthor ? alex : sam, is_author: isAuthor, rating: 4 })
  vi.mocked(realApi).mockImplementation(async (path, options = {}) => {
    if (path === '/social/posts/' && !options.method) return { posts: current ? [current] : [] }
    if (path === '/social/posts/7/' && !options.method) {
      if (!current) throw Object.assign(new Error('Post not found.'), { status: 404 })
      return { post: current }
    }
    if (path === '/social/posts/7/' && options.method === 'PATCH') {
      if (onPatch) return onPatch(options.body)
      current = { ...current, ...options.body }
      return { post: current }
    }
    if (path === '/social/posts/7/' && options.method === 'DELETE') {
      if (onDelete) return onDelete()
      current = null
      return { ok: true }
    }
    throw new Error(`unexpected call to api(${path}, ${options.method})`)
  })
}

function calls(method) {
  return vi.mocked(realApi).mock.calls.filter(([, options = {}]) => options.method === method)
}

describe('editing a food post (#51)', () => {
  test('the author sees Edit post on their own post', async () => {
    mockOwnPost()
    renderApp('/community/posts/7')
    expect(await screen.findByRole('link', { name: /Edit post/ })).toHaveAttribute('href', '/community/posts/7/edit')
  })

  test('another student sees no Edit post or Delete post', async () => {
    mockOwnPost({ isAuthor: false })
    renderApp('/community/posts/7')
    expect(await screen.findByRole('heading', { level: 1, name: "Joe's Pizza" })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Edit post/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Delete post/ })).not.toBeInTheDocument()
  })

  test('the edit form opens with the post’s current information', async () => {
    mockOwnPost()
    renderApp('/community/posts/7/edit')
    const form = await screen.findByRole('form', { name: 'Edit your food post' })
    expect(within(form).getByLabelText(/Restaurant or food place/)).toHaveValue("Joe's Pizza")
    expect(within(form).getByLabelText(/Description or recommendation/)).toHaveValue('Grab a plain slice.')
    expect(within(form).getByLabelText(/Cuisine/)).toHaveValue('Pizza')
    expect(within(form).getByLabelText(/Rating/)).toHaveValue('4')
    expect(within(form).getByLabelText(/Location/)).toHaveValue('7 Carmine St')
  })

  test('saving sends the changes and the post page shows them', async () => {
    mockOwnPost()
    renderApp('/community/posts/7')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('link', { name: /Edit post/ }))
    const description = await screen.findByLabelText(/Description or recommendation/)
    await user.clear(description)
    await user.type(description, 'Get the grandma slice.')
    await user.selectOptions(screen.getByLabelText(/Rating/), '')
    await user.click(screen.getByRole('button', { name: /Save changes/ }))

    expect(calls('PATCH')).toEqual([['/social/posts/7/', { method: 'PATCH', body: {
      place_name: "Joe's Pizza", description: 'Get the grandma slice.', location: '7 Carmine St', cuisine: 'Pizza', rating: null,
    } }]])
    expect(await screen.findByRole('status')).toHaveTextContent('Saved your changes.')
    const card = screen.getByRole('article', { name: "Joe's Pizza" })
    expect(within(card).getByText('Get the grandma slice.')).toBeInTheDocument()
    expect(within(card).queryByLabelText(/Rated/)).not.toBeInTheDocument()
  })

  test('saved changes show in the community feed', async () => {
    mockOwnPost()
    renderApp('/community/posts/7/edit')
    const user = userEvent.setup()
    const name = await screen.findByLabelText(/Restaurant or food place/)
    await user.clear(name)
    await user.type(name, "Joe's Pizza Carmine")
    await user.click(screen.getByRole('button', { name: /Save changes/ }))
    await user.click(await screen.findByRole('link', { name: /Back to food feed/ }))
    expect(await within(await screen.findByRole('region', { name: 'Food feed' })).findByRole('link', { name: "Joe's Pizza Carmine" })).toBeInTheDocument()
  })

  test('server validation errors show next to the fields and nothing is lost', async () => {
    mockOwnPost({ onPatch: async () => { throw Object.assign(new Error('Invalid'), { errors: { place_name: ['Enter the name of the restaurant or food place.'] } }) } })
    renderApp('/community/posts/7/edit')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText(/Description or recommendation/), ' More.')
    await user.click(screen.getByRole('button', { name: /Save changes/ }))
    expect(await screen.findByText('Enter the name of the restaurant or food place.')).toBeInTheDocument()
    expect(screen.getByLabelText(/Description or recommendation/)).toHaveValue('Grab a plain slice. More.')
    expect(screen.getByRole('form', { name: 'Edit your food post' })).toBeInTheDocument()
  })

  test('a general error shows when saving fails without field errors', async () => {
    mockOwnPost({ onPatch: async () => { throw new Error('Network down.') } })
    renderApp('/community/posts/7/edit')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Save changes/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Network down.')
    expect(screen.getByRole('button', { name: /Save changes/ })).toBeEnabled()
  })

  test('cancel goes back to the post without saving', async () => {
    mockOwnPost()
    renderApp('/community/posts/7/edit')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText(/Description or recommendation/), ' Changed.')
    await user.click(screen.getByRole('link', { name: 'Cancel' }))
    expect(await screen.findByRole('heading', { level: 1, name: "Joe's Pizza" })).toBeInTheDocument()
    expect(screen.getByText('Grab a plain slice.')).toBeInTheDocument()
    expect(calls('PATCH')).toEqual([])
  })

  test('another student opening the edit page directly sees it is not available', async () => {
    mockOwnPost({ isAuthor: false })
    renderApp('/community/posts/7/edit')
    expect(await screen.findByText('This post isn’t available')).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Edit your food post' })).not.toBeInTheDocument()
  })

  test('if the server refuses the edit, the page says the post is not available', async () => {
    mockOwnPost({ onPatch: async () => { throw Object.assign(new Error('Post not found.'), { status: 404 }) } })
    renderApp('/community/posts/7/edit')
    await userEvent.setup().click(await screen.findByRole('button', { name: /Save changes/ }))
    expect(await screen.findByText('This post isn’t available')).toBeInTheDocument()
  })
})

describe('deleting a food post (#52)', () => {
  test('clicking Delete post asks to confirm before deleting anything', async () => {
    mockOwnPost()
    renderApp('/community/posts/7')
    await userEvent.setup().click(await screen.findByRole('button', { name: /Delete post/ }))
    expect(screen.getByRole('alert')).toHaveTextContent("Delete your post about Joe's Pizza? This can’t be undone.")
    expect(calls('DELETE')).toEqual([])
  })

  test('confirming deletes the post and it is gone from the feed', async () => {
    mockOwnPost()
    renderApp('/community/posts/7')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Delete post/ }))
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(calls('DELETE')).toEqual([['/social/posts/7/', { method: 'DELETE' }]])
    expect(await screen.findByText("Deleted your post about Joe's Pizza.")).toBeInTheDocument()
    expect(await within(await screen.findByRole('region', { name: 'Food feed' })).findByText('No posts yet')).toBeInTheDocument()
  })

  test('cancelling leaves the post unchanged', async () => {
    mockOwnPost()
    renderApp('/community/posts/7')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Delete post/ }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('article', { name: "Joe's Pizza" })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Delete post/ })).toBeEnabled()
    expect(calls('DELETE')).toEqual([])
  })

  test('a failed delete keeps the post and lets you try again', async () => {
    let fail = true
    mockOwnPost({ onDelete: async () => { if (fail) throw new Error('Network down.'); return { ok: true } } })
    renderApp('/community/posts/7')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Delete post/ }))
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(await screen.findByText('Couldn’t delete this post. Try again.')).toBeInTheDocument()
    expect(screen.getByRole('article', { name: "Joe's Pizza" })).toBeInTheDocument()
    fail = false
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(await screen.findByText("Deleted your post about Joe's Pizza.")).toBeInTheDocument()
  })
})
