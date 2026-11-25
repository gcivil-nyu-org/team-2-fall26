import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { EventDetailPage, EventsPage } from './EventsPage'

vi.mock('./api', async (original) => ({ ...await original(), api: vi.fn() }))
afterEach(() => { cleanup(); vi.mocked(api).mockReset() })
const event = { id: 1, title: 'Career workshop', host: 'Career Hub', location: 'Brooklyn',
  starts_at: '2026-11-16T23:00:00Z', ends_at: '2026-11-17T01:00:00Z',
  categories: ['Professional & Career Development'], source_url: 'https://engage.nyu.edu/event/123',
  description: '<script>unsafe()</script>', status: 'confirmed' }
const result = { events: [event], count: 1, page: 1, pages: 1, categories: event.categories,
  last_synced_at: '2026-11-16T12:00:00Z', stale: false }
function renderList() { render(<MemoryRouter><EventsPage /></MemoryRouter>) }

test('shows source, Eastern time, details link and refresh time', async () => {
  vi.mocked(api).mockResolvedValue(result)
  renderList()
  expect(await screen.findByRole('heading', { name: 'Career workshop' })).toBeInTheDocument()
  expect(screen.getByText(/6:00 PM EST/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'View event' })).toHaveAttribute('href', '/events/1')
  expect(screen.getByText(/Last refreshed/)).toBeInTheDocument()
})

test('applies search, category and career filters, then clears them', async () => {
  const user = userEvent.setup()
  vi.mocked(api).mockResolvedValue(result)
  renderList()
  await screen.findByText('1 event found')
  await user.type(screen.getByLabelText('Search events'), 'resume')
  await user.selectOptions(screen.getByLabelText('Category'), event.categories[0])
  await user.click(screen.getByLabelText('Career development'))
  await user.click(screen.getByRole('button', { name: 'Apply filters' }))
  await waitFor(() => expect(vi.mocked(api).mock.calls.at(-1)[0]).toContain('career=true'))
  const query = new URLSearchParams(vi.mocked(api).mock.calls.at(-1)[0].split('?')[1])
  expect(query.get('q')).toBe('resume')
  expect(query.get('category')).toBe(event.categories[0])
  await user.click(screen.getByRole('button', { name: 'Clear filters' }))
  await waitFor(() => expect(vi.mocked(api).mock.calls.at(-1)[0]).toBe('/events/?'))
})

test('handles failure, retry, and empty uninitialized feed', async () => {
  const user = userEvent.setup()
  vi.mocked(api).mockRejectedValueOnce(new Error('Offline')).mockResolvedValue({ ...result, events: [], count: 0, last_synced_at: null, stale: true })
  renderList()
  expect(await screen.findByRole('alert')).toHaveTextContent('Offline')
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText('No upcoming events found')).toBeInTheDocument()
  expect(screen.getByText(/Events have not been imported/)).toBeInTheDocument()
})

test('pagination preserves filters', async () => {
  const user = userEvent.setup()
  vi.mocked(api).mockResolvedValue({ ...result, pages: 2, count: 25 })
  render(<MemoryRouter initialEntries={['/events?career=true']}><EventsPage /></MemoryRouter>)
  await screen.findByText('25 events found')
  await user.click(screen.getByRole('button', { name: 'Next' }))
  await waitFor(() => expect(vi.mocked(api).mock.calls.at(-1)[0]).toBe('/events/?career=true&page=2'))
})

test('cancelled detail is readable and descriptions render as text', async () => {
  vi.mocked(api).mockResolvedValue({ event: { ...event, status: 'cancelled' } })
  const { container } = render(<MemoryRouter initialEntries={['/events/1']}><Routes><Route path="/events/:eventId" element={<EventDetailPage />} /></Routes></MemoryRouter>)
  expect(await screen.findByRole('alert')).toHaveTextContent('cancelled')
  expect(screen.getByText('<script>unsafe()</script>')).toBeInTheDocument()
  expect(container.querySelector('script')).toBeNull()
  expect(screen.getByRole('link', { name: 'View on NYU Engage' })).toHaveAttribute('href', event.source_url)
})


test('refreshes future events when returning to the page', async () => {
  vi.mocked(api).mockResolvedValueOnce(result).mockResolvedValue({ ...result, events: [], count: 0 })
  renderList()
  await screen.findByText('1 event found')
  window.dispatchEvent(new Event('focus'))
  expect(await screen.findByText('No upcoming events found')).toBeInTheDocument()
})


test('saves an upcoming event and confirms it before offering removal', async () => {
  const user = userEvent.setup()
  vi.mocked(api).mockResolvedValueOnce({ ...result, events: [{ ...event, starts_at: '2099-11-16T23:00:00Z', is_saved: false }] })
    .mockResolvedValueOnce({ saved: true }).mockResolvedValueOnce({ saved: false })
  renderList()
  await user.click(await screen.findByRole('button', { name: 'Save to calendar' }))
  expect(api).toHaveBeenLastCalledWith('/events/1/save/', { method: 'PUT' })
  await user.click(await screen.findByRole('button', { name: 'Remove from calendar' }))
  expect(api).toHaveBeenLastCalledWith('/events/1/save/', { method: 'DELETE' })
  expect(await screen.findByRole('button', { name: 'Save to calendar' })).toBeInTheDocument()
})
