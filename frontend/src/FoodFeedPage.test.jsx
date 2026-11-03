import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { api as realApi } from './api'
import { FoodFeedPage } from './FoodFeedPage'

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

function feed() {
  return screen.getByRole('region', { name: 'Food feed' })
}

describe('viewing the food feed', () => {
  test('shows each post with its place, details, rating and author', async () => {
    mockFeed([post()])
    render(<FoodFeedPage />)
    const card = await screen.findByRole('article', { name: "Joe's Pizza" })
    expect(within(card).getByText('Grab a plain slice.')).toBeInTheDocument()
    expect(within(card).getByText('Pizza')).toBeInTheDocument()
    expect(within(card).getByText(/7 Carmine St/)).toBeInTheDocument()
    expect(within(card).getByLabelText('Rated 5 out of 5')).toBeInTheDocument()
    expect(within(card).getByText(/Sam Lee/)).toBeInTheDocument()
  })

  test('leaves out optional details a post does not have', async () => {
    mockFeed([post({ location: '', cuisine: '', rating: null })])
    render(<FoodFeedPage />)
    const card = await screen.findByRole('article', { name: "Joe's Pizza" })
    expect(within(card).queryByText('Pizza')).not.toBeInTheDocument()
    expect(within(card).queryByLabelText(/out of 5/)).not.toBeInTheDocument()
  })

  test('shows a message when there are no posts yet', async () => {
    mockFeed([])
    render(<FoodFeedPage />)
    expect(await screen.findByText('No posts yet')).toBeInTheDocument()
  })

  test('shows an error with a working retry when the feed fails to load', async () => {
    vi.mocked(realApi).mockRejectedValueOnce(new Error('Something went wrong.'))
    render(<FoodFeedPage />)
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
    render(<FoodFeedPage />)
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
    render(<FoodFeedPage />)
    await screen.findByText('No posts yet')

    await userEvent.type(screen.getByLabelText('Restaurant or food place'), 'Somewhere')
    await userEvent.type(screen.getByLabelText('Description or recommendation'), 'Good.')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    await waitFor(() => expect(onCreate).toHaveBeenCalled())
    expect(onCreate.mock.calls[0][0].rating).toBeNull()
  })

  test('shows server validation errors next to the matching fields', async () => {
    mockFeed([])
    render(<FoodFeedPage />)
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
    render(<FoodFeedPage />)
    await screen.findByText('No posts yet')
    vi.mocked(realApi).mockRejectedValueOnce(Object.assign(new Error('Authentication required.'), { status: 401, errors: {} }))

    await userEvent.type(screen.getByLabelText('Restaurant or food place'), 'Somewhere')
    await userEvent.type(screen.getByLabelText('Description or recommendation'), 'Good.')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Authentication required.')
  })
})
