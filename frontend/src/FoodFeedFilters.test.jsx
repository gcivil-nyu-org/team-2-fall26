import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { api } from './api'
import { FoodFeedPage, filterFoodPosts } from './FoodFeedPage'

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal()),
  api: vi.fn(),
}))

const author = { id: 1, first_name: 'Alex', last_name: 'Smith', email: 'alex@nyu.edu', profile_picture: null }
const posts = [
  { id: 3, place_name: "Joe's Pizza", description: 'The plain slice is excellent', cuisine: 'Italian', location: 'Manhattan', rating: 5 },
  { id: 2, place_name: 'Tasty Dumplings', description: 'Get the pork dumplings', cuisine: 'Chinese', location: 'Chinatown Manhattan', rating: 4 },
  { id: 1, place_name: 'Green Garden', description: 'Delicious vegan bowls', cuisine: 'Vegetarian', location: 'Brooklyn', rating: null },
].map((post) => ({ ...post, author, is_saved: false, comment_count: 0, created_at: '2026-11-10T18:00:00Z' }))

afterEach(() => {
  cleanup()
  vi.mocked(api).mockReset()
})

function setup(data = posts) {
  vi.mocked(api).mockResolvedValue({ posts: data })
  render(<MemoryRouter><FoodFeedPage /></MemoryRouter>)
  return userEvent.setup()
}

function names() {
  return within(screen.getByRole('region', { name: 'Food feed' }))
    .queryAllByRole('article').map((element) => element.getAttribute('aria-label'))
}

test('initially shows the whole feed newest first', async () => {
  setup()
  await screen.findByRole('article', { name: "Joe's Pizza" })
  expect(names()).toEqual(["Joe's Pizza", 'Tasty Dumplings', 'Green Garden'])
  expect(screen.getByLabelText('3 matching recommendations')).toHaveTextContent('3')
})

test('search matches place names regardless of case or surrounding spaces', async () => {
  const user = setup()
  await screen.findByRole('article', { name: "Joe's Pizza" })
  await user.type(screen.getByRole('searchbox', { name: 'Search recommendations' }), '  dUmPlingS  ')
  expect(names()).toEqual(['Tasty Dumplings'])
})

test('search also matches keywords in recommendations, not only place names', async () => {
  const user = setup()
  await screen.findByRole('article', { name: "Joe's Pizza" })
  await user.type(screen.getByRole('searchbox', { name: 'Search recommendations' }), 'vegan')
  expect(names()).toEqual(['Green Garden'])
})

test('cuisine dropdown is generated from available posts and filters exactly', async () => {
  const user = setup()
  await screen.findByRole('article', { name: "Joe's Pizza" })
  expect(within(screen.getByLabelText('Filter by cuisine')).getAllByRole('option').map((item) => item.textContent)).toEqual(['All cuisines', 'Chinese', 'Italian', 'Vegetarian'])
  await user.selectOptions(screen.getByLabelText('Filter by cuisine'), 'Chinese')
  expect(names()).toEqual(['Tasty Dumplings'])
})

test('location filtering is case insensitive and matches partial locations', async () => {
  const user = setup()
  await screen.findByRole('article', { name: "Joe's Pizza" })
  await user.type(screen.getByLabelText('Filter by location'), 'manHAT')
  expect(names()).toEqual(["Joe's Pizza", 'Tasty Dumplings'])
})

test('multiple filters combine rather than replace each other', async () => {
  const user = setup()
  await screen.findByRole('article', { name: "Joe's Pizza" })
  await user.selectOptions(screen.getByLabelText('Filter by cuisine'), 'Italian')
  await user.type(screen.getByLabelText('Filter by location'), 'Manhattan')
  await user.type(screen.getByRole('searchbox', { name: 'Search recommendations' }), 'plain')
  expect(names()).toEqual(["Joe's Pizza"])
  await user.type(screen.getByRole('searchbox', { name: 'Search recommendations' }), 'sushi')
  expect(names()).toEqual([])
  expect(screen.getByText('No matching recommendations')).toBeInTheDocument()
  expect(screen.getByLabelText('0 matching recommendations')).toHaveTextContent('0')
  await user.click(screen.getByRole('button', { name: 'Clear filters' }))
  expect(names()).toEqual(["Joe's Pizza", 'Tasty Dumplings', 'Green Garden'])
})

test('empty feed retains its distinct first-post empty state', async () => {
  setup([])
  expect(await screen.findByText('No posts yet')).toBeInTheDocument()
  expect(screen.queryByText('No matching recommendations')).not.toBeInTheDocument()
})

test('pure filter tolerates optional blank cuisine and location fields', () => {
  const data = [{ place_name: 'No extras', description: 'Tasty food', cuisine: '', location: '' }]
  expect(filterFoodPosts(data, { query: 'tasty' })).toEqual(data)
  expect(filterFoodPosts(data, { cuisine: 'Italian' })).toEqual([])
  expect(filterFoodPosts(data, { location: 'NYU' })).toEqual([])
})
