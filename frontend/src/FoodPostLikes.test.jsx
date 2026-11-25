import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { api } from './api'
import { FoodFeedPage, FoodPostPage, SavedPostsPage } from './FoodFeedPage'

vi.mock('./api', async (importOriginal) => ({ ...(await importOriginal()), api: vi.fn() }))

const author = { id: 2, first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu', profile_picture: null }
function post(overrides = {}) {
  return {
    id: 7, place_name: "Joe's Pizza", description: 'Great slices',
    cuisine: 'Italian', location: 'Manhattan', rating: 5, author,
    created_at: '2026-11-10T18:00:00Z', is_saved: false,
    comment_count: 0, is_liked: false, like_count: 0, ...overrides,
  }
}

afterEach(() => {
  cleanup()
  vi.mocked(api).mockReset()
})

function fakeApi({ feed = [post()], saved = [], detail = post(), failLike = false } = {}) {
  let liked = detail.is_liked
  let count = detail.like_count
  vi.mocked(api).mockImplementation(async (path, options = {}) => {
    if (path === '/social/posts/' && !options.method) return { posts: feed }
    if (path === '/social/posts/saved/' && !options.method) return { posts: saved }
    if (path === '/social/posts/7/' && !options.method) return { post: detail }
    if (path === '/social/posts/7/comments/' && !options.method) return { comments: [] }
    if (path === '/social/posts/7/like/' && ['PUT', 'DELETE'].includes(options.method)) {
      if (failLike) throw new Error('Unable to like the post.')
      if (options.method === 'PUT' && !liked) { liked = true; count += 1 }
      if (options.method === 'DELETE' && liked) { liked = false; count -= 1 }
      return { is_liked: liked, like_count: count }
    }
    throw new Error(`unexpected api call: ${path}`)
  })
}

function renderPage(route = '/community') {
  return render(<MemoryRouter initialEntries={[route]}>
    <Routes>
      <Route path="/community" element={<FoodFeedPage />} />
      <Route path="/community/posts/:postId" element={<FoodPostPage />} />
      <Route path="/community/saved" element={<SavedPostsPage />} />
    </Routes>
  </MemoryRouter>)
}

test('like count and pressed state appear in the food feed', async () => {
  fakeApi({ feed: [post({ is_liked: true, like_count: 3 })] })
  renderPage()
  const button = await screen.findByRole('button', { name: "Unlike Joe's Pizza" })
  expect(button).toHaveAttribute('aria-pressed', 'true')
  expect(button).toHaveTextContent('3 likes')
})

test('liking and unliking updates the server-controlled count', async () => {
  fakeApi()
  renderPage()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: "Like Joe's Pizza" }))
  expect(api).toHaveBeenCalledWith('/social/posts/7/like/', { method: 'PUT' })
  expect(await screen.findByRole('button', { name: "Unlike Joe's Pizza" })).toHaveTextContent('1 like')
  await user.click(screen.getByRole('button', { name: "Unlike Joe's Pizza" }))
  expect(api).toHaveBeenCalledWith('/social/posts/7/like/', { method: 'DELETE' })
  expect(await screen.findByRole('button', { name: "Like Joe's Pizza" })).toHaveTextContent('0 likes')
})

test('a failed like leaves the state unchanged and displays an error', async () => {
  fakeApi({ failLike: true })
  renderPage()
  await userEvent.setup().click(await screen.findByRole('button', { name: "Like Joe's Pizza" }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to like the post.')
  expect(screen.getByRole('button', { name: "Like Joe's Pizza" })).toHaveAttribute('aria-pressed', 'false')
  expect(screen.getByRole('button', { name: "Like Joe's Pizza" })).toHaveTextContent('0 likes')
})

test('like toggle also appears on individual post detail', async () => {
  fakeApi()
  renderPage('/community/posts/7')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: "Like Joe's Pizza" }))
  expect(await screen.findByRole('button', { name: "Unlike Joe's Pizza" })).toHaveTextContent('1 like')
})

test('like toggle also works on the saved recommendations page', async () => {
  fakeApi({ saved: [post({ is_saved: true })] })
  renderPage('/community/saved')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: "Like Joe's Pizza" }))
  expect(await screen.findByRole('button', { name: "Unlike Joe's Pizza" })).toHaveTextContent('1 like')
  expect(screen.getByRole('button', { name: "Unsave Joe's Pizza" })).toBeInTheDocument()
})

test('likes and saves use separate controls in food cards', async () => {
  fakeApi()
  renderPage()
  await screen.findByRole('button', { name: "Like Joe's Pizza" })
  expect(screen.getByRole('button', { name: "Save Joe's Pizza" })).toHaveAttribute('aria-pressed', 'false')
  expect(screen.getByRole('button', { name: "Like Joe's Pizza" })).toHaveAttribute('aria-pressed', 'false')
})

test.each([
  ['/community', false], ['/community', true],
  ['/community/posts/7', false], ['/community/posts/7', true],
  ['/community/saved', false], ['/community/saved', true],
])('overlapping like and save preserve both results on %s (save first: %s)', async (route, saveFirst) => {
  const initiallySaved = route === '/community/saved'
  const initial = post({ is_saved: initiallySaved })
  let finishLike, finishSave
  vi.mocked(api).mockImplementation(async (path, options = {}) => {
    if (path === '/social/posts/' && !options.method) return { posts: [initial] }
    if (path === '/social/posts/saved/' && !options.method) return { posts: [initial] }
    if (path === '/social/posts/7/' && !options.method) return { post: initial }
    if (path === '/social/posts/7/comments/' && !options.method) return { comments: [] }
    if (path.endsWith('/like/')) return new Promise(resolve => { finishLike = resolve })
    if (path.endsWith('/save/')) return new Promise(resolve => { finishSave = resolve })
    throw new Error(`unexpected: ${path}`)
  })
  renderPage(route)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: "Like Joe's Pizza" }))
  await user.click(screen.getByRole('button', { name: `${initiallySaved ? 'Unsave' : 'Save'} Joe's Pizza` }))
  if (saveFirst) {
    finishSave({ saved: !initiallySaved })
    if (initiallySaved) await screen.findByText('No saved recommendations yet')
    else await screen.findByRole('button', { name: "Unsave Joe's Pizza" })
    finishLike({ is_liked: true, like_count: 1 })
  } else {
    finishLike({ is_liked: true, like_count: 1 })
    expect(await screen.findByRole('button', { name: "Unlike Joe's Pizza" })).toHaveTextContent('1 like')
    finishSave({ saved: !initiallySaved })
  }
  if (initiallySaved) {
    await waitFor(() => expect(screen.queryByRole('article', { name: "Joe's Pizza" })).not.toBeInTheDocument())
  } else {
    await screen.findByRole('button', { name: "Unsave Joe's Pizza" })
    expect(await screen.findByRole('button', { name: "Unlike Joe's Pizza" })).toHaveTextContent('1 like')
  }
})
