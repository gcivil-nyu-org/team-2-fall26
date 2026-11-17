import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { api } from './api'
import { AvailabilityPage, CalendarPage } from './StudyPages'

vi.mock('./api', async (original) => ({ ...await original(), api: vi.fn() }))
afterEach(() => { cleanup(); vi.mocked(api).mockReset() })

const session = { id: 7, starts_at: '2026-11-02T09:00:00Z', ends_at: '2026-11-02T10:00:00Z', is_locked: false, assignment: { title: 'Essay' }, course: { id: 1, code: 'SWE', name: 'Software' } }
const week = { week_start: '2026-11-02', week_end: '2026-11-09', previous_week: '2026-10-26', next_week: '2026-11-09', availability_configured: true, sessions: [session] }
function openCalendar() {
  vi.mocked(api).mockResolvedValue(week)
  render(<MemoryRouter initialEntries={['/calendar?week=2026-11-02']}><CalendarPage /></MemoryRouter>)
}
async function edit() {
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Reschedule Essay' }))
  return user
}
function changeTime(start = '2026-11-03T10:00', end = '2026-11-03T11:00') {
  fireEvent.input(screen.getByLabelText('Start (Eastern)'), { target: { value: start } })
  fireEvent.input(screen.getByLabelText('End (Eastern)'), { target: { value: end } })
}

test('lock and unlock update the badge and send the explicit target state', async () => {
  openCalendar()
  const user = userEvent.setup()
  const button = await screen.findByRole('button', { name: 'Lock Essay' })
  vi.mocked(api).mockResolvedValueOnce({ ...session, is_locked: true })
  await user.click(button)
  expect(api).toHaveBeenLastCalledWith('/study/sessions/7/', { method: 'PATCH', body: { is_locked: true } })
  expect(await screen.findByText('Locked')).toBeInTheDocument()
  vi.mocked(api).mockResolvedValueOnce({ ...session, is_locked: false })
  await user.click(screen.getByRole('button', { name: 'Unlock Essay' }))
  await waitFor(() => expect(screen.queryByText('Locked')).not.toBeInTheDocument())
  expect(api).toHaveBeenLastCalledWith('/study/sessions/7/', { method: 'PATCH', body: { is_locked: false } })
})

test('cancel closes an Eastern-prefilled editor without sending a mutation', async () => {
  openCalendar()
  const user = await edit()
  expect(screen.getByLabelText('Start (Eastern)')).toHaveValue('2026-11-02T04:00')
  changeTime()
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByLabelText('Start (Eastern)')).not.toBeInTheDocument()
  expect(vi.mocked(api).mock.calls.filter(([, options]) => options?.method === 'PATCH')).toHaveLength(0)
})

test('reschedule refreshes the visible calendar after saving', async () => {
  openCalendar()
  const user = await edit()
  changeTime()
  vi.mocked(api).mockResolvedValueOnce({ ...session, starts_at: '2026-11-03T10:00:00Z', ends_at: '2026-11-03T11:00:00Z' })
  vi.mocked(api).mockResolvedValueOnce({ ...week, sessions: [] })
  await user.click(screen.getByRole('button', { name: 'Save new time' }))
  expect(api).toHaveBeenCalledWith('/study/sessions/7/', { method: 'PATCH', body: { starts_at: '2026-11-03T10:00', ends_at: '2026-11-03T11:00', confirm_warnings: false } })
  expect(await screen.findByText('No events this week')).toBeInTheDocument()
})

test('warnings require a second explicit confirmation and editing clears confirmation', async () => {
  openCalendar()
  const user = await edit()
  changeTime()
  const conflict = Object.assign(new Error('Review these warnings before moving the session.'), { status: 409, warnings: ['This time overlaps another study session.', 'This time falls outside your weekly availability.'] })
  vi.mocked(api).mockRejectedValueOnce(conflict)
  await user.click(screen.getByRole('button', { name: 'Save new time' }))
  expect(await screen.findByText('This time overlaps another study session.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Move anyway' })).toBeInTheDocument()
  changeTime('2026-11-03T12:00', '2026-11-03T13:00')
  expect(screen.queryByRole('button', { name: 'Move anyway' })).not.toBeInTheDocument()
  vi.mocked(api).mockRejectedValueOnce(conflict)
  await user.click(screen.getByRole('button', { name: 'Save new time' }))
  await screen.findByRole('button', { name: 'Move anyway' })
  expect(vi.mocked(api).mock.calls.at(-1)[1].body.confirm_warnings).toBe(false)
  vi.mocked(api).mockResolvedValueOnce(session)
  await user.click(screen.getByRole('button', { name: 'Move anyway' }))
  expect(vi.mocked(api).mock.calls.findLast(([, options]) => options?.method === 'PATCH')[1].body.confirm_warnings).toBe(true)
})

test('failed lock leaves the session unlocked and displays an error', async () => {
  openCalendar()
  const user = userEvent.setup()
  const button = await screen.findByRole('button', { name: 'Lock Essay' })
  vi.mocked(api).mockRejectedValueOnce(new Error('Unable to save.'))
  await user.click(button)
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to save.')
  expect(screen.getByRole('button', { name: 'Lock Essay' })).toBeEnabled()
  expect(screen.queryByText('Locked')).not.toBeInTheDocument()
})

const generated = { id: 9, starts_at: '2026-11-03T14:00:00Z', ends_at: '2026-11-03T16:00:00Z', is_locked: false, assignment: { id: 2, title: 'Report' }, course: { id: 1, code: 'SWE', name: 'Software' } }
function mockGenerate(result) {
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/study/generate/') {
      if (result instanceof Error) throw result
      return result
    }
    return path.startsWith('/study/calendar/') && !options ? week : undefined
  })
}

test('generating asks first, then posts once and refreshes the calendar', async () => {
  openCalendar()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Generate study plan' }))
  expect(screen.getByRole('group', { name: 'Confirm study plan' })).toHaveTextContent(/locked sessions and past sessions stay/i)
  expect(vi.mocked(api).mock.calls.filter(([path]) => path === '/study/generate/')).toHaveLength(0)

  mockGenerate({ sessions: [generated], shortfalls: [], skipped: [] })
  const calendarLoads = vi.mocked(api).mock.calls.length
  await user.click(screen.getByRole('button', { name: 'Generate' }))
  expect(api).toHaveBeenCalledWith('/study/generate/', { method: 'POST' })
  expect(await screen.findByText('Created 1 study session')).toBeInTheDocument()
  expect(screen.getByText(/runs through Nov 3, 11:00 AM EST/)).toBeInTheDocument()
  await waitFor(() => expect(vi.mocked(api).mock.calls.slice(calendarLoads).some(([path]) => path.startsWith('/study/calendar/'))).toBe(true))
  expect(screen.queryByRole('group', { name: 'Confirm study plan' })).not.toBeInTheDocument()
})

test('cancelling the plan sends nothing', async () => {
  openCalendar()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Generate study plan' }))
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('group', { name: 'Confirm study plan' })).not.toBeInTheDocument()
  expect(vi.mocked(api).mock.calls.filter(([path]) => path === '/study/generate/')).toHaveLength(0)
})

test('shortfalls and skipped assignments are explained instead of dropped', async () => {
  openCalendar()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Generate study plan' }))
  mockGenerate({
    sessions: [generated],
    shortfalls: [{ id: 2, title: 'Report', due_date: '2026-11-04T04:59:00+00:00', course: { id: 1, code: 'SWE', name: 'Software' }, hours_short: 1.25 }],
    skipped: [{ id: 3, title: 'Reading', due_date: null, course: { id: 1, code: '', name: 'Software' }, reason: 'Add a deadline to include this in your plan.' }],
  })
  await user.click(screen.getByRole('button', { name: 'Generate' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Report (SWE) needs 1.25 more hours before Nov 3, 11:59 PM EST')
  expect(screen.getByText('Reading (Software): Add a deadline to include this in your plan.')).toBeInTheDocument()
})

test('a failed generation shows the error and keeps the confirm open to retry', async () => {
  openCalendar()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Generate study plan' }))
  mockGenerate(new Error('Set your weekly availability before generating a study plan.'))
  await user.click(screen.getByRole('button', { name: 'Generate' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Set your weekly availability')
  expect(screen.getByRole('group', { name: 'Confirm study plan' })).toBeInTheDocument()
})

test('without availability, generating explains what to do instead of doing nothing', async () => {
  vi.mocked(api).mockResolvedValue({ ...week, availability_configured: false })
  render(<MemoryRouter initialEntries={['/calendar?week=2026-11-02']}><CalendarPage /></MemoryRouter>)
  const button = await screen.findByRole('button', { name: 'Generate study plan' })
  expect(button).toBeEnabled()
  await userEvent.setup().click(button)
  expect(screen.getByRole('alert')).toHaveTextContent('Set your weekly availability before generating a study plan.')
  expect(screen.queryByRole('group', { name: 'Confirm study plan' })).not.toBeInTheDocument()
  expect(vi.mocked(api).mock.calls.filter(([path]) => path === '/study/generate/')).toHaveLength(0)
})

test('exam prep sessions are labelled and can be locked like any session', async () => {
  const prep = { ...session, id: 8, assignment: null, exam: { id: 4, title: 'Midterm' } }
  vi.mocked(api).mockResolvedValue({ ...week, sessions: [prep] })
  render(<MemoryRouter initialEntries={['/calendar?week=2026-11-02']}><CalendarPage /></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'Midterm prep' })).toBeInTheDocument()
  vi.mocked(api).mockResolvedValueOnce({ ...prep, is_locked: true })
  await userEvent.setup().click(screen.getByRole('button', { name: 'Lock Midterm prep' }))
  expect(api).toHaveBeenLastCalledWith('/study/sessions/8/', { method: 'PATCH', body: { is_locked: true } })
})

test('marking a session complete and reopening it sends the explicit state', async () => {
  openCalendar()
  const user = userEvent.setup()
  vi.mocked(api).mockResolvedValueOnce({ ...session, is_complete: true })
  await user.click(await screen.findByRole('button', { name: 'Mark Essay complete' }))
  expect(api).toHaveBeenLastCalledWith('/study/sessions/7/', { method: 'PATCH', body: { is_complete: true } })
  expect(await screen.findByText('Completed')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Essay' }).closest('article')).toHaveClass('calendar-session--complete')
  expect(screen.getByText('1 of 1 study hours completed')).toBeInTheDocument()

  vi.mocked(api).mockResolvedValueOnce({ ...session, is_complete: false })
  await user.click(screen.getByRole('button', { name: 'Reopen Essay' }))
  expect(api).toHaveBeenLastCalledWith('/study/sessions/7/', { method: 'PATCH', body: { is_complete: false } })
  await waitFor(() => expect(screen.queryByText('Completed')).not.toBeInTheDocument())
  expect(screen.getByText('0 of 1 study hours completed')).toBeInTheDocument()
})

test('completed sessions from the server stay marked after a reload', async () => {
  const other = { ...session, id: 8, starts_at: '2026-11-03T14:00:00Z', ends_at: '2026-11-03T15:30:00Z', assignment: { title: 'Report' } }
  vi.mocked(api).mockResolvedValue({ ...week, sessions: [{ ...session, is_complete: true }, other] })
  render(<MemoryRouter initialEntries={['/calendar?week=2026-11-02']}><CalendarPage /></MemoryRouter>)
  expect(await screen.findByRole('button', { name: 'Reopen Essay' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Mark Report complete' })).toBeInTheDocument()
  expect(screen.getByText('1 of 2.5 study hours completed')).toBeInTheDocument()
})

test('a failed completion update leaves the session as it was', async () => {
  openCalendar()
  const user = userEvent.setup()
  vi.mocked(api).mockRejectedValueOnce(new Error('Could not update the session.'))
  await user.click(await screen.findByRole('button', { name: 'Mark Essay complete' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not update the session.')
  expect(screen.queryByText('Completed')).not.toBeInTheDocument()
})

test('adding a second block on the same day saves without an overlap', async () => {
  vi.mocked(api).mockResolvedValue({ timezone: 'America/New_York', configured: false, blocks: [] })
  render(<MemoryRouter><AvailabilityPage /></MemoryRouter>)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Add time on Tuesday' }))
  await user.click(screen.getByRole('button', { name: 'Add time on Tuesday' }))
  vi.mocked(api).mockImplementation(async (path, options) => ({ timezone: 'America/New_York', configured: true, blocks: options?.body?.blocks ?? [] }))
  await user.click(screen.getByRole('button', { name: 'Save availability' }))
  expect(api).toHaveBeenLastCalledWith('/study/availability/', { method: 'PUT', body: { blocks: [
    { weekday: 1, start_time: '09:00', end_time: '10:00' },
    { weekday: 1, start_time: '10:00', end_time: '11:00' },
  ] } })
})
