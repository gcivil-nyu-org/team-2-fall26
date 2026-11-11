import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { api as realApi } from './api'
import AccountSettings from './AccountSettings'
import NotificationSettings, { leadTimeLabel, notificationSummary } from './NotificationSettings'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, api: vi.fn() }
})

afterEach(() => {
  cleanup()
  vi.mocked(realApi).mockReset()
})

const defaults = { study_reminders_enabled: true, study_reminder_minutes: 60 }
const options = { study_reminder_minutes: [15, 30, 60, 120] }

// The server answers a save with the settings it actually stored.
function mockSettings(overrides = {}, onSave) {
  vi.mocked(realApi).mockImplementation(async (path, request) => {
    if (path !== '/profile/notifications/') throw new Error(`unexpected call to api(${path})`)
    if (request?.method === 'PUT') return onSave ? onSave(request) : { notifications: request.body, options }
    return { notifications: { ...defaults, ...overrides }, options }
  })
}

async function openEditor(user) {
  await user.click(await screen.findByRole('button', { name: /edit notifications/i }))
}

// #37: a student chooses whether and how early study reminders appear.
describe('notification settings on the Account settings page', () => {
  test('the Account settings page includes the Notifications section', async () => {
    mockSettings()
    render(<MemoryRouter><AccountSettings onAccountClosed={vi.fn()} /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Notifications' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Take a break' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /permanently delete your account/i })).toBeInTheDocument()
  })

  test('starts collapsed with a one-line summary of the default', async () => {
    mockSettings()
    render(<NotificationSettings />)
    expect(await screen.findByText(/reminds you 1 hour before a study session starts/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /edit notifications/i })).toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
  })

  test('shows a loading message until the settings arrive', async () => {
    mockSettings()
    render(<NotificationSettings />)
    expect(screen.getByRole('status')).toHaveTextContent(/loading your notification settings/i)
    await screen.findByRole('button', { name: /edit notifications/i })
  })

  test('a failed load shows an error and a working Try again', async () => {
    const user = userEvent.setup()
    vi.mocked(realApi).mockRejectedValueOnce(new Error('Network down'))
    render(<NotificationSettings />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn.t load your notification settings/i)
    mockSettings()
    await user.click(screen.getByRole('button', { name: /try again/i }))
    expect(await screen.findByRole('button', { name: /edit notifications/i })).toBeInTheDocument()
  })

  test('an expired session says so', async () => {
    const error = new Error('Unauthorized')
    error.status = 401
    vi.mocked(realApi).mockRejectedValueOnce(error)
    render(<NotificationSettings />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/session expired/i)
  })

  test('the summary reflects reminders being off', async () => {
    mockSettings({ study_reminders_enabled: false })
    render(<NotificationSettings />)
    expect(await screen.findByText(/study session reminders are off/i)).toBeInTheDocument()
  })

  test('the summary reflects a saved lead time', async () => {
    mockSettings({ study_reminder_minutes: 15 })
    render(<NotificationSettings />)
    expect(await screen.findByText(/reminds you 15 minutes before/i)).toBeInTheDocument()
  })

  test('lead times read naturally', () => {
    expect(leadTimeLabel(15)).toBe('15 minutes')
    expect(leadTimeLabel(30)).toBe('30 minutes')
    expect(leadTimeLabel(60)).toBe('1 hour')
    expect(leadTimeLabel(120)).toBe('2 hours')
    expect(notificationSummary({ study_reminders_enabled: true, study_reminder_minutes: 120 })).toMatch(/2 hours before/)
  })

  test('Edit notifications opens the switch and the lead-time choices', async () => {
    const user = userEvent.setup()
    mockSettings({ study_reminder_minutes: 30 })
    render(<NotificationSettings />)
    await openEditor(user)
    expect(screen.getByRole('switch', { name: /study session reminders/i })).toBeChecked()
    const select = screen.getByRole('combobox', { name: /remind me/i })
    expect(select).toHaveValue('30')
    expect(within(select).getAllByRole('option').map((option) => option.textContent))
      .toEqual(['15 minutes before', '30 minutes before', '1 hour before', '2 hours before'])
  })

  test('the lead-time choices are whatever the server offers', async () => {
    const user = userEvent.setup()
    vi.mocked(realApi).mockResolvedValue({ notifications: defaults, options: { study_reminder_minutes: [10, 60, 180] } })
    render(<NotificationSettings />)
    await openEditor(user)
    expect(within(screen.getByRole('combobox', { name: /remind me/i })).getAllByRole('option').map((option) => option.textContent))
      .toEqual(['10 minutes before', '1 hour before', '180 minutes before'])
  })

  test('says reminders only appear in the app, not by email or phone', async () => {
    const user = userEvent.setup()
    mockSettings()
    render(<NotificationSettings />)
    await openEditor(user)
    expect(screen.getByText(/appear in semesterpilot on your dashboard/i)).toBeInTheDocument()
    expect(screen.getByText(/doesn.t send emails or phone notifications/i)).toBeInTheDocument()
  })

  test('the lead-time choice is unavailable while reminders are off', async () => {
    const user = userEvent.setup()
    mockSettings()
    render(<NotificationSettings />)
    await openEditor(user)
    expect(screen.getByRole('combobox', { name: /remind me/i })).toBeEnabled()
    await user.click(screen.getByRole('switch', { name: /study session reminders/i }))
    expect(screen.getByRole('combobox', { name: /remind me/i })).toBeDisabled()
    await user.click(screen.getByRole('switch', { name: /study session reminders/i }))
    expect(screen.getByRole('combobox', { name: /remind me/i })).toBeEnabled()
  })

  test('saving a new lead time sends it, then collapses with the new summary and a confirmation', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn(async (request) => ({ notifications: request.body, options }))
    mockSettings({}, onSave)
    render(<NotificationSettings />)
    await openEditor(user)

    await user.selectOptions(screen.getByRole('combobox', { name: /remind me/i }), '120')
    await user.click(screen.getByRole('button', { name: /save notification settings/i }))

    expect(await screen.findByText(/notification settings have been saved/i)).toBeInTheDocument()
    expect(screen.getByText(/reminds you 2 hours before/i)).toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      method: 'PUT',
      body: { study_reminders_enabled: true, study_reminder_minutes: 120 },
    }))
  })

  test('turning reminders off and saving shows the off summary', async () => {
    const user = userEvent.setup()
    mockSettings()
    render(<NotificationSettings />)
    await openEditor(user)
    await user.click(screen.getByRole('switch', { name: /study session reminders/i }))
    await user.click(screen.getByRole('button', { name: /save notification settings/i }))
    expect(await screen.findByText(/study session reminders are off/i)).toBeInTheDocument()
  })

  test('the lead time is kept when reminders are turned off and back on', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn(async (request) => ({ notifications: request.body, options }))
    mockSettings({ study_reminder_minutes: 30 }, onSave)
    render(<NotificationSettings />)
    await openEditor(user)
    await user.click(screen.getByRole('switch', { name: /study session reminders/i }))
    await user.click(screen.getByRole('switch', { name: /study session reminders/i }))
    await user.click(screen.getByRole('button', { name: /save notification settings/i }))
    await screen.findByText(/notification settings have been saved/i)
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ body: { study_reminders_enabled: true, study_reminder_minutes: 30 } }))
  })

  test('nothing is sent until the student saves', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn(async (request) => ({ notifications: request.body, options }))
    mockSettings({}, onSave)
    render(<NotificationSettings />)
    await openEditor(user)
    await user.click(screen.getByRole('switch', { name: /study session reminders/i }))
    await user.selectOptions(screen.getByRole('combobox', { name: /remind me/i }), '15')
    expect(onSave).not.toHaveBeenCalled()
  })

  test('Cancel throws away unsaved changes and closes the form', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    mockSettings({}, onSave)
    render(<NotificationSettings />)
    await openEditor(user)
    await user.click(screen.getByRole('switch', { name: /study session reminders/i }))
    await user.click(within(screen.getByRole('form', { name: 'Notifications' })).getByRole('button', { name: /^cancel$/i }))

    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.getByText(/reminds you 1 hour before a study session starts/i)).toBeInTheDocument()
    await openEditor(user)
    expect(screen.getByRole('switch', { name: /study session reminders/i })).toBeChecked()
    expect(onSave).not.toHaveBeenCalled()
  })

  test('a failed save shows the error, stays open, keeps the choices, and does not claim success', async () => {
    const user = userEvent.setup()
    mockSettings({}, async () => { throw new Error('Something went wrong.') })
    render(<NotificationSettings />)
    await openEditor(user)
    await user.click(screen.getByRole('switch', { name: /study session reminders/i }))
    await user.click(screen.getByRole('button', { name: /save notification settings/i }))

    expect(await screen.findByText('Something went wrong.')).toBeInTheDocument()
    expect(screen.queryByText(/notification settings have been saved/i)).not.toBeInTheDocument()
    expect(screen.getByRole('switch', { name: /study session reminders/i })).not.toBeChecked()
  })

  test('a server-side rejection of the lead time is shown to the student', async () => {
    const user = userEvent.setup()
    const rejection = new Error('Bad request')
    rejection.status = 400
    rejection.errors = { study_reminder_minutes: ['Choose how early to be reminded.'] }
    mockSettings({}, async () => { throw rejection })
    render(<NotificationSettings />)
    await openEditor(user)
    await user.click(screen.getByRole('button', { name: /save notification settings/i }))
    expect(await screen.findByText('Choose how early to be reminded.')).toBeInTheDocument()
  })

  test('after a failed save, Cancel goes back to what was last saved', async () => {
    const user = userEvent.setup()
    mockSettings({}, async () => { throw new Error('Something went wrong.') })
    render(<NotificationSettings />)
    await openEditor(user)
    await user.click(screen.getByRole('switch', { name: /study session reminders/i }))
    await user.click(screen.getByRole('button', { name: /save notification settings/i }))
    await screen.findByText('Something went wrong.')

    await user.click(within(screen.getByRole('form', { name: 'Notifications' })).getByRole('button', { name: /^cancel$/i }))
    expect(screen.getByText(/reminds you 1 hour before a study session starts/i)).toBeInTheDocument()
    expect(screen.queryByText('Something went wrong.')).not.toBeInTheDocument()
  })
})
