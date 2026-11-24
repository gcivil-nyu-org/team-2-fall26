import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { api as realApi } from './api'
import { FoodFeedPage, FoodPostPage, PREVIEW_LENGTH, previewText, SavedPostsPage } from './FoodFeedPage'

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
    is_saved: false,
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
      <Route path="/community/saved" element={<SavedPostsPage />} />
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

describe('saving food recommendations', () => {
  function mockSaving({ posts = [], saved = [], detail = null, failSave = false } = {}) {
    vi.mocked(realApi).mockImplementation(async (path, options = {}) => {
      if (path === '/social/posts/' && !options.method) return { posts }
      if (path === '/social/posts/saved/' && !options.method) return { posts: saved }
      if (detail && path === `/social/posts/${detail.id}/` && !options.method) return { post: detail }
      const match = path.match(/^\/social\/posts\/(\d+)\/save\/$/)
      if (match && ['PUT', 'DELETE'].includes(options.method)) {
        if (failSave) throw new Error('Could not save that post.')
        return { saved: options.method === 'PUT' }
      }
      throw new Error(`unexpected call to api(${path})`)
    })
  }

  test('saving a post from the feed marks it saved, and saving again unsaves it', async () => {
    mockSaving({ posts: [post({ id: 7 })] })
    renderFeed()
    const user = userEvent.setup()
    const save = await screen.findByRole('button', { name: "Save Joe's Pizza" })
    expect(save).toHaveAttribute('aria-pressed', 'false')
    await user.click(save)
    expect(realApi).toHaveBeenLastCalledWith('/social/posts/7/save/', { method: 'PUT' })
    const unsave = await screen.findByRole('button', { name: "Unsave Joe's Pizza" })
    expect(unsave).toHaveAttribute('aria-pressed', 'true')
    expect(unsave).toHaveTextContent('Saved')
    await user.click(unsave)
    expect(realApi).toHaveBeenLastCalledWith('/social/posts/7/save/', { method: 'DELETE' })
    expect(await screen.findByRole('button', { name: "Save Joe's Pizza" })).toHaveAttribute('aria-pressed', 'false')
  })

  test('a post you already saved shows as saved', async () => {
    mockSaving({ posts: [post({ is_saved: true })] })
    renderFeed()
    expect(await screen.findByRole('button', { name: "Unsave Joe's Pizza" })).toHaveAttribute('aria-pressed', 'true')
  })

  test('a failed save shows an error and leaves the button as it was', async () => {
    mockSaving({ posts: [post({ id: 7 })], failSave: true })
    renderFeed()
    await userEvent.setup().click(await screen.findByRole('button', { name: "Save Joe's Pizza" }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save that post.')
    expect(screen.getByRole('button', { name: "Save Joe's Pizza" })).toHaveAttribute('aria-pressed', 'false')
  })

  test('a post can be saved from its own page', async () => {
    mockSaving({ detail: post({ id: 7 }) })
    renderApp('/community/posts/7')
    await userEvent.setup().click(await screen.findByRole('button', { name: "Save Joe's Pizza" }))
    expect(realApi).toHaveBeenLastCalledWith('/social/posts/7/save/', { method: 'PUT' })
    expect(await screen.findByRole('button', { name: "Unsave Joe's Pizza" })).toBeInTheDocument()
  })

  test('the feed links to your saved recommendations', async () => {
    mockSaving({ posts: [], saved: [post({ id: 7, is_saved: true })] })
    renderApp('/community')
    await userEvent.setup().click(await screen.findByRole('link', { name: /Saved recommendations/ }))
    const list = await screen.findByRole('region', { name: 'Saved recommendations' })
    expect(within(list).getByRole('article', { name: "Joe's Pizza" })).toBeInTheDocument()
  })

  test('the saved page lists your saved posts and unsaving one removes it', async () => {
    const pizza = post({ id: 7, is_saved: true })
    const falafel = post({ id: 8, place_name: "Mamoun's Falafel", is_saved: true })
    mockSaving({ saved: [pizza, falafel] })
    renderApp('/community/saved')
    const list = await screen.findByRole('region', { name: 'Saved recommendations' })
    expect(within(list).getAllByRole('article').map((card) => card.getAttribute('aria-label'))).toEqual(["Joe's Pizza", "Mamoun's Falafel"])
    expect(within(list).getByText('2')).toBeInTheDocument()
    await userEvent.setup().click(within(list).getByRole('button', { name: "Unsave Joe's Pizza" }))
    expect(realApi).toHaveBeenLastCalledWith('/social/posts/7/save/', { method: 'DELETE' })
    await waitFor(() => expect(within(list).queryByRole('article', { name: "Joe's Pizza" })).not.toBeInTheDocument())
    expect(within(list).getByRole('article', { name: "Mamoun's Falafel" })).toBeInTheDocument()
  })

  test('the saved page says when nothing is saved yet', async () => {
    mockSaving({ saved: [] })
    renderApp('/community/saved')
    expect(await screen.findByText('No saved recommendations yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Browse the food feed' })).toHaveAttribute('href', '/community')
  })

  test('the saved page offers a working retry when it fails to load', async () => {
    vi.mocked(realApi).mockRejectedValueOnce(new Error('Network down.'))
    renderApp('/community/saved')
    expect(await screen.findByRole('alert')).toHaveTextContent('Network down.')
    mockSaving({ saved: [post({ is_saved: true })] })
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('article', { name: "Joe's Pizza" })).toBeInTheDocument()
  })
})
