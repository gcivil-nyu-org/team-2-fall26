import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { api as realApi } from './api'
import AccountSettings from './AccountSettings'
import PrivacySettings, { privacySummary } from './PrivacySettings'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, api: vi.fn() }
})

afterEach(() => {
  cleanup()
  vi.mocked(realApi).mockReset()
})

const profile = { first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: null, bio: '' }

function mockProfile(overrides = {}, onPrivacy) {
  vi.mocked(realApi).mockImplementation(async (path, options) => {
    if (path === '/profile/') return { user: { ...profile, show_email: true, show_bio: true, show_profile_picture: true, ...overrides } }
    if (path === '/profile/privacy/') return onPrivacy ? onPrivacy(options) : { user: profile }
    throw new Error(`unexpected call to api(${path})`)
  })
}

async function openPrivacy(user) {
  await user.click(await screen.findByRole('button', { name: /edit privacy/i }))
}

// #31: a student chooses what other students can see (email, bio, photo).
describe('privacy settings on the Account settings page', () => {
  test('the Account settings page includes the Privacy section', async () => {
    mockProfile()
    render(<MemoryRouter><AccountSettings onAccountClosed={vi.fn()} /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Privacy' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Take a break' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /permanently delete your account/i })).toBeInTheDocument()
  })

  test('starts collapsed with a one-line summary', async () => {
    mockProfile()
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    expect(await screen.findByText(/other students can see your name, email, bio and photo/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /edit privacy/i })).toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
  })

  test('shows a loading message until the settings arrive', async () => {
    mockProfile()
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    expect(screen.getByRole('status')).toHaveTextContent(/loading your privacy settings/i)
    await screen.findByRole('button', { name: /edit privacy/i })
  })

  test('a failed load shows an error and a working Try again', async () => {
    const user = userEvent.setup()
    vi.mocked(realApi).mockRejectedValueOnce(new Error('Network down'))
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn.t load your privacy settings/i)
    mockProfile()
    await user.click(screen.getByRole('button', { name: /try again/i }))
    expect(await screen.findByRole('button', { name: /edit privacy/i })).toBeInTheDocument()
  })

  test('an expired session says so', async () => {
    const error = new Error('Unauthorized')
    error.status = 401
    vi.mocked(realApi).mockRejectedValueOnce(error)
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent(/session expired/i)
  })

  test('the summary reflects what is already hidden', async () => {
    mockProfile({ show_email: false, show_profile_picture: false })
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    expect(await screen.findByText(/hidden from other students: email and photo/i)).toBeInTheDocument()
  })

  test('the summary says so when everything is hidden', async () => {
    mockProfile({ show_email: false, show_bio: false, show_profile_picture: false })
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    expect(await screen.findByText(/other students only see your name/i)).toBeInTheDocument()
  })

  test('summary wording for one hidden detail', () => {
    expect(privacySummary({ show_email: true, show_bio: false, show_profile_picture: true }))
      .toBe('Hidden from other students: bio. Your name is always visible.')
  })

  test('Edit privacy opens one switch per detail, and the name is not a choice', async () => {
    const user = userEvent.setup()
    mockProfile({ show_bio: false })
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    await openPrivacy(user)
    expect(screen.getAllByRole('switch')).toHaveLength(3)
    expect(screen.getByRole('switch', { name: /show my email address/i })).toBeChecked()
    expect(screen.getByRole('switch', { name: /show my bio/i })).not.toBeChecked()
    expect(screen.getByRole('switch', { name: /show my profile photo/i })).toBeChecked()
    expect(screen.getByText(/your name is always visible/i)).toBeInTheDocument()
  })

  test('saving sends all three choices, then collapses with the new summary and a confirmation', async () => {
    const user = userEvent.setup()
    const onPrivacy = vi.fn(async () => ({ user: profile }))
    mockProfile({}, onPrivacy)
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    await openPrivacy(user)

    await user.click(screen.getByRole('switch', { name: /show my bio/i }))
    await user.click(screen.getByRole('switch', { name: /show my email address/i }))
    await user.click(screen.getByRole('button', { name: /save privacy settings/i }))

    expect(await screen.findByText(/privacy settings have been saved/i)).toBeInTheDocument()
    expect(screen.getByText(/hidden from other students: email and bio/i)).toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(onPrivacy).toHaveBeenCalledWith(expect.objectContaining({
      method: 'PUT',
      body: { show_email: false, show_bio: false, show_profile_picture: true },
    }))
  })

  test('nothing is sent until the student saves', async () => {
    const user = userEvent.setup()
    const onPrivacy = vi.fn(async () => ({ user: profile }))
    mockProfile({}, onPrivacy)
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    await openPrivacy(user)
    await user.click(screen.getByRole('switch', { name: /show my bio/i }))
    expect(onPrivacy).not.toHaveBeenCalled()
  })

  test('Cancel throws away unsaved changes and closes the form', async () => {
    const user = userEvent.setup()
    const onPrivacy = vi.fn(async () => ({ user: profile }))
    mockProfile({}, onPrivacy)
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    await openPrivacy(user)
    await user.click(screen.getByRole('switch', { name: /show my bio/i }))
    await user.click(screen.getByRole('button', { name: /^cancel$/i }))

    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(screen.getByText(/other students can see your name, email, bio and photo/i)).toBeInTheDocument()
    await openPrivacy(user)
    expect(screen.getByRole('switch', { name: /show my bio/i })).toBeChecked()
    expect(onPrivacy).not.toHaveBeenCalled()
  })

  test('a failed save shows an error, stays open, keeps the choices, and does not claim success', async () => {
    const user = userEvent.setup()
    mockProfile({}, async () => { throw new Error('Something went wrong.') })
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    await openPrivacy(user)

    await user.click(screen.getByRole('switch', { name: /show my bio/i }))
    await user.click(screen.getByRole('button', { name: /save privacy settings/i }))

    expect(await screen.findByText('Something went wrong.')).toBeInTheDocument()
    expect(screen.queryByText(/privacy settings have been saved/i)).not.toBeInTheDocument()
    expect(screen.getByRole('switch', { name: /show my bio/i })).not.toBeChecked()
  })

  test('after a failed save, Cancel goes back to what was last saved', async () => {
    const user = userEvent.setup()
    mockProfile({}, async () => { throw new Error('Something went wrong.') })
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    await openPrivacy(user)
    await user.click(screen.getByRole('switch', { name: /show my bio/i }))
    await user.click(screen.getByRole('button', { name: /save privacy settings/i }))
    await screen.findByText('Something went wrong.')

    await user.click(within(screen.getByRole('form', { name: 'Privacy' })).getByRole('button', { name: /^cancel$/i }))
    expect(screen.getByText(/other students can see your name, email, bio and photo/i)).toBeInTheDocument()
    expect(screen.queryByText('Something went wrong.')).not.toBeInTheDocument()
  })
})

// A student with no name who hides their email would show up as a blank "?".
describe('asking for a name when the email is hidden', () => {
  const nameless = { first_name: '', last_name: '' }

  test('no note when the email is shown, even without a name', async () => {
    mockProfile(nameless)
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    await screen.findByRole('button', { name: /edit privacy/i })
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  test('no note when the email is hidden but there is a name', async () => {
    mockProfile({ show_email: false })
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    await screen.findByRole('button', { name: /edit privacy/i })
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  test('a saved hidden email with no name shows the note with a link to Edit profile', async () => {
    mockProfile({ ...nameless, show_email: false })
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    const note = await screen.findByRole('note')
    expect(note).toHaveTextContent(/add your name/i)
    expect(within(note).getByRole('link', { name: /edit profile/i })).toHaveAttribute('href', '/profile')
  })

  test('turning the email switch off while nameless shows the note right away, and on hides it', async () => {
    const user = userEvent.setup()
    mockProfile(nameless)
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    await openPrivacy(user)
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
    await user.click(screen.getByRole('switch', { name: /show my email address/i }))
    expect(screen.getByRole('note')).toHaveTextContent(/add your name/i)
    await user.click(screen.getByRole('switch', { name: /show my email address/i }))
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  test('with a name, hiding the email never shows the note, even while editing', async () => {
    const user = userEvent.setup()
    mockProfile()
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    await openPrivacy(user)
    await user.click(screen.getByRole('switch', { name: /show my email address/i }))
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  test('hiding bio or photo without a name does not show the note', async () => {
    const user = userEvent.setup()
    mockProfile(nameless)
    render(<MemoryRouter><PrivacySettings /></MemoryRouter>)
    await openPrivacy(user)
    await user.click(screen.getByRole('switch', { name: /show my bio/i }))
    await user.click(screen.getByRole('switch', { name: /show my profile photo/i }))
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })
})
