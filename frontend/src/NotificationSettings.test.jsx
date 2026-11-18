import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { api as realApi } from './api'
import AccountSettings from './AccountSettings'
import { ALERTS_CHANGED } from './alerts'
import NotificationSettings, { deadlineLeadLabel, leadTimeLabel, notificationSummary } from './NotificationSettings'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, api: vi.fn() }
})

afterEach(() => {
  cleanup()
  vi.mocked(realApi).mockReset()
})

const defaults = {
  study_reminders_enabled: true,
  study_reminder_minutes: 60,
  deadline_reminders_enabled: true,
  deadline_reminder_hours: 24,
  friend_request_alerts_enabled: true,
  message_alerts_enabled: true,
}
const options = { study_reminder_minutes: [15, 30, 60, 120], deadline_reminder_hours: [6, 24, 48, 72] }

// The server answers a save with the settings it actually stored.
function mockSettings(overrides = {}, onSave) {
  vi.mocked(realApi).mockImplementation(async (path, request) => {
    if (path !== '/profile/notifications/') throw new Error(`unexpected call to api(${path})`)
    if (request?.method === 'PUT') return onSave ? onSave(request) : { notifications: request.body, options }
    return { notifications: { ...defaults, ...overrides }, options }
  })
}

const echo = () => vi.fn(async (request) => ({ notifications: request.body, options }))

async function openEditor(user) {
  await user.click(await screen.findByRole('button', { name: /edit notifications/i }))
}

const save = (user) => user.click(screen.getByRole('button', { name: /save notification settings/i }))
const toggle = (user, name) => user.click(screen.getByRole('switch', { name }))
const summaryLines = () => within(screen.getByRole('list')).getAllByRole('listitem').map((item) => item.textContent)

// #37: a student chooses which reminders and alerts they get, and how early.
describe('notification settings on the Account settings page', () => {
  test('the Account settings page includes the Notifications section', async () => {
    mockSettings()
    render(<MemoryRouter><AccountSettings onAccountClosed={vi.fn()} /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Notifications' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Take a break' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /permanently delete your account/i })).toBeInTheDocument()
  })

  test('starts collapsed with a line for each kind of alert', async () => {
    mockSettings()
    render(<NotificationSettings />)
    await screen.findByRole('button', { name: /edit notifications/i })
    expect(summaryLines()).toEqual([
      'Study sessions: reminded 1 hour before they start',
      'Assignments and exams: reminded 24 hours before they’re due',
      'Friend requests: on',
      'New messages: on',
    ])
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

  test('the summary reflects every setting being off', async () => {
    mockSettings({
      study_reminders_enabled: false, deadline_reminders_enabled: false,
      friend_request_alerts_enabled: false, message_alerts_enabled: false,
    })
    render(<NotificationSettings />)
    await screen.findByRole('button', { name: /edit notifications/i })
    expect(summaryLines()).toEqual([
      'Study sessions: off', 'Assignments and exams: off', 'Friend requests: off', 'New messages: off',
    ])
  })

  test('the summary reflects saved lead times', async () => {
    mockSettings({ study_reminder_minutes: 15, deadline_reminder_hours: 72 })
    render(<NotificationSettings />)
    await screen.findByRole('button', { name: /edit notifications/i })
    expect(summaryLines().slice(0, 2)).toEqual([
      'Study sessions: reminded 15 minutes before they start',
      'Assignments and exams: reminded 72 hours before they’re due',
    ])
  })

  test('lead times read naturally', () => {
    expect(leadTimeLabel(15)).toBe('15 minutes')
    expect(leadTimeLabel(30)).toBe('30 minutes')
    expect(leadTimeLabel(60)).toBe('1 hour')
    expect(leadTimeLabel(120)).toBe('2 hours')
    expect(leadTimeLabel(180)).toBe('3 hours')
    expect(deadlineLeadLabel(1)).toBe('1 hour')
    expect(deadlineLeadLabel(24)).toBe('24 hours')
    expect(notificationSummary({ ...defaults, study_reminder_minutes: 120 })[0]).toMatch(/2 hours before/)
  })

  test('Edit notifications opens a switch for each alert and the lead-time choices', async () => {
    const user = userEvent.setup()
    mockSettings({ study_reminder_minutes: 30, deadline_reminder_hours: 48 })
    render(<NotificationSettings />)
    await openEditor(user)
    for (const name of [/study session reminders/i, /assignment and exam reminders/i, /friend request alerts/i, /new message alerts/i]) {
      expect(screen.getByRole('switch', { name })).toBeChecked()
    }
    const study = screen.getByRole('combobox', { name: /study reminder timing/i })
    expect(study).toHaveValue('30')
    expect(within(study).getAllByRole('option').map((option) => option.textContent))
      .toEqual(['15 minutes before', '30 minutes before', '1 hour before', '2 hours before'])
    const deadline = screen.getByRole('combobox', { name: /due-date reminder timing/i })
    expect(deadline).toHaveValue('48')
    expect(within(deadline).getAllByRole('option').map((option) => option.textContent))
      .toEqual(['6 hours before', '24 hours before', '48 hours before', '72 hours before'])
  })

  test('the lead-time choices are whatever the server offers', async () => {
    const user = userEvent.setup()
    vi.mocked(realApi).mockResolvedValue({
      notifications: defaults,
      options: { study_reminder_minutes: [10, 60, 180], deadline_reminder_hours: [1, 12] },
    })
    render(<NotificationSettings />)
    await openEditor(user)
    expect(within(screen.getByRole('combobox', { name: /study reminder timing/i })).getAllByRole('option').map((option) => option.textContent))
      .toEqual(['10 minutes before', '1 hour before', '3 hours before'])
    expect(within(screen.getByRole('combobox', { name: /due-date reminder timing/i })).getAllByRole('option').map((option) => option.textContent))
      .toEqual(['1 hour before', '12 hours before'])
  })

  test('says everything stays inside the app, not email or phone', async () => {
    const user = userEvent.setup()
    mockSettings()
    render(<NotificationSettings />)
    await openEditor(user)
    expect(screen.getByText(/appears inside semesterpilot/i)).toBeInTheDocument()
    expect(screen.getByText(/doesn.t send emails or phone notifications/i)).toBeInTheDocument()
  })

  test('each lead-time choice is unavailable only while its own reminder is off', async () => {
    const user = userEvent.setup()
    mockSettings()
    render(<NotificationSettings />)
    await openEditor(user)
    const study = screen.getByRole('combobox', { name: /study reminder timing/i })
    const deadline = screen.getByRole('combobox', { name: /due-date reminder timing/i })
    expect(study).toBeEnabled()
    expect(deadline).toBeEnabled()

    await toggle(user, /study session reminders/i)
    expect(study).toBeDisabled()
    expect(deadline).toBeEnabled()

    await toggle(user, /study session reminders/i)
    await toggle(user, /assignment and exam reminders/i)
    expect(study).toBeEnabled()
    expect(deadline).toBeDisabled()
  })

  test('saving refreshes the sidebar badges right away, and a failed save does not', async () => {
    const user = userEvent.setup()
    const refreshed = vi.fn()
    window.addEventListener(ALERTS_CHANGED, refreshed)
    try {
      mockSettings({}, echo())
      render(<NotificationSettings />)
      await openEditor(user)
      await toggle(user, /new message alerts/i)
      await save(user)
      expect(await screen.findByText(/notification settings have been saved/i)).toBeInTheDocument()
      expect(refreshed).toHaveBeenCalledTimes(1)

      cleanup()
      refreshed.mockClear()
      mockSettings({}, () => { throw Object.assign(new Error('nope'), { errors: {} }) })
      render(<NotificationSettings />)
      await openEditor(user)
      await toggle(user, /new message alerts/i)
      await save(user)
      await screen.findByRole('alert')
      expect(refreshed).not.toHaveBeenCalled()
    } finally {
      window.removeEventListener(ALERTS_CHANGED, refreshed)
    }
  })

  test('saving sends every setting, then collapses with the new summary and a confirmation', async () => {
    const user = userEvent.setup()
    const onSave = echo()
    mockSettings({}, onSave)
    render(<NotificationSettings />)
    await openEditor(user)

    await user.selectOptions(screen.getByRole('combobox', { name: /study reminder timing/i }), '120')
    await user.selectOptions(screen.getByRole('combobox', { name: /due-date reminder timing/i }), '72')
    await toggle(user, /friend request alerts/i)
    await save(user)

    expect(await screen.findByText(/notification settings have been saved/i)).toBeInTheDocument()
    expect(summaryLines()).toEqual([
      'Study sessions: reminded 2 hours before they start',
      'Assignments and exams: reminded 72 hours before they’re due',
      'Friend requests: off',
      'New messages: on',
    ])
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      method: 'PUT',
      body: { ...defaults, study_reminder_minutes: 120, deadline_reminder_hours: 72, friend_request_alerts_enabled: false },
    }))
  })

  test.each([
    [/study session reminders/i, 'study_reminders_enabled'],
    [/assignment and exam reminders/i, 'deadline_reminders_enabled'],
    [/friend request alerts/i, 'friend_request_alerts_enabled'],
    [/new message alerts/i, 'message_alerts_enabled'],
  ])('the %s switch changes only its own setting', async (name, field) => {
    const user = userEvent.setup()
    const onSave = echo()
    mockSettings({}, onSave)
    render(<NotificationSettings />)
    await openEditor(user)
    await toggle(user, name)
    await save(user)
    await screen.findByText(/notification settings have been saved/i)
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ body: { ...defaults, [field]: false } }))
  })

  test('the lead times are kept when a reminder is turned off and back on', async () => {
    const user = userEvent.setup()
    const onSave = echo()
    mockSettings({ study_reminder_minutes: 30, deadline_reminder_hours: 6 }, onSave)
    render(<NotificationSettings />)
    await openEditor(user)
    await toggle(user, /study session reminders/i)
    await toggle(user, /study session reminders/i)
    await toggle(user, /assignment and exam reminders/i)
    await toggle(user, /assignment and exam reminders/i)
    await save(user)
    await screen.findByText(/notification settings have been saved/i)
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      body: { ...defaults, study_reminder_minutes: 30, deadline_reminder_hours: 6 },
    }))
  })

  test('nothing is sent until the student saves', async () => {
    const user = userEvent.setup()
    const onSave = echo()
    mockSettings({}, onSave)
    render(<NotificationSettings />)
    await openEditor(user)
    await toggle(user, /study session reminders/i)
    await toggle(user, /new message alerts/i)
    await user.selectOptions(screen.getByRole('combobox', { name: /due-date reminder timing/i }), '6')
    expect(onSave).not.toHaveBeenCalled()
  })

  test('Cancel throws away unsaved changes and closes the form', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    mockSettings({}, onSave)
    render(<NotificationSettings />)
    await openEditor(user)
    await toggle(user, /study session reminders/i)
    await toggle(user, /new message alerts/i)
    await user.click(within(screen.getByRole('form', { name: 'Notifications' })).getByRole('button', { name: /^cancel$/i }))

    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(summaryLines()[0]).toBe('Study sessions: reminded 1 hour before they start')
    expect(summaryLines()[3]).toBe('New messages: on')
    await openEditor(user)
    expect(screen.getByRole('switch', { name: /study session reminders/i })).toBeChecked()
    expect(screen.getByRole('switch', { name: /new message alerts/i })).toBeChecked()
    expect(onSave).not.toHaveBeenCalled()
  })

  test('a failed save shows the error, stays open, keeps the choices, and does not claim success', async () => {
    const user = userEvent.setup()
    mockSettings({}, async () => { throw new Error('Something went wrong.') })
    render(<NotificationSettings />)
    await openEditor(user)
    await toggle(user, /study session reminders/i)
    await save(user)

    expect(await screen.findByText('Something went wrong.')).toBeInTheDocument()
    expect(screen.queryByText(/notification settings have been saved/i)).not.toBeInTheDocument()
    expect(screen.getByRole('switch', { name: /study session reminders/i })).not.toBeChecked()
  })

  test.each([
    ['study_reminder_minutes', 'Choose how early to be reminded.'],
    ['deadline_reminder_hours', 'Choose how early to be reminded.'],
    ['message_alerts_enabled', 'Choose on or off.'],
  ])('a server-side rejection of %s is shown to the student', async (field, message) => {
    const user = userEvent.setup()
    const rejection = new Error('Bad request')
    rejection.status = 400
    rejection.errors = { [field]: [message] }
    mockSettings({}, async () => { throw rejection })
    render(<NotificationSettings />)
    await openEditor(user)
    await save(user)
    expect(await screen.findByText(message)).toBeInTheDocument()
  })

  test('after a failed save, Cancel goes back to what was last saved', async () => {
    const user = userEvent.setup()
    mockSettings({}, async () => { throw new Error('Something went wrong.') })
    render(<NotificationSettings />)
    await openEditor(user)
    await toggle(user, /study session reminders/i)
    await save(user)
    await screen.findByText('Something went wrong.')

    await user.click(within(screen.getByRole('form', { name: 'Notifications' })).getByRole('button', { name: /^cancel$/i }))
    expect(summaryLines()[0]).toBe('Study sessions: reminded 1 hour before they start')
    expect(screen.queryByText('Something went wrong.')).not.toBeInTheDocument()
  })
})
