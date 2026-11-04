import { afterEach, describe, expect, test, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { api as realApi } from './api'
import { AppShell, AuthContext, Dashboard, ProfilePage } from './App'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, api: vi.fn() }
})

afterEach(() => {
  cleanup()
  vi.mocked(realApi).mockReset()
})

function renderWithAuth(ui, { session } = {}) {
  const authValue = {
    session: session ?? { loading: false, authenticated: true, user: { first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: null } },
    refresh: vi.fn(),
    setSession: vi.fn(),
  }
  return {
    ...render(
      <MemoryRouter>
        <AuthContext.Provider value={authValue}>{ui}</AuthContext.Provider>
      </MemoryRouter>,
    ),
    authValue,
  }
}

describe('sidebar avatar', () => {
  test('shows the uploaded picture when the user has one', () => {
    renderWithAuth(<AppShell>content</AppShell>, {
      session: { loading: false, authenticated: true, user: { first_name: 'Sanchu', email: 'sanchu@nyu.edu', profile_picture: '/media/profile-pictures/sanchu.png' } },
    })
    const avatarImg = screen.getByRole('link', { name: /edit your profile/i }).querySelector('img')
    expect(avatarImg).toHaveAttribute('src', '/media/profile-pictures/sanchu.png')
  })

  test('falls back to an initial when there is no picture', () => {
    renderWithAuth(<AppShell>content</AppShell>, {
      session: { loading: false, authenticated: true, user: { first_name: 'Sanchu', email: 'sanchu@nyu.edu', profile_picture: null } },
    })
    const profileLink = screen.getByRole('link', { name: /edit your profile/i })
    expect(profileLink.querySelector('img')).toBeNull()
    expect(profileLink).toHaveTextContent('S')
  })
})

describe('profile picture upload on the Edit Profile page', () => {
  function mockProfileLoad(user) {
    vi.mocked(realApi).mockImplementation(async (path) => {
      if (path === '/profile/') return { user }
      throw new Error(`unexpected call to api(${path})`)
    })
  }

  test('uploading a picture shows it as the avatar and reveals a remove option', async () => {
    const user = userEvent.setup()
    mockProfileLoad({ first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: null })
    renderWithAuth(<ProfilePage />)

    await waitFor(() => expect(screen.getByLabelText(/upload a profile photo/i)).toBeInTheDocument())
    expect(screen.queryByText(/remove/i)).not.toBeInTheDocument()

    vi.mocked(realApi).mockImplementationOnce(async (path, options) => {
      expect(path).toBe('/profile/picture/')
      expect(options.body).toBeInstanceOf(FormData)
      return { user: { first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: '/media/profile-pictures/new.png' } }
    })
    vi.mocked(realApi).mockImplementationOnce(async (path) => {
      if (path === '/profile/') return { user: { first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: '/media/profile-pictures/new.png' } }
      throw new Error(`unexpected call to api(${path})`)
    })

    const file = new File(['pixel'], 'avatar.png', { type: 'image/png' })
    await user.upload(screen.getByTestId('profile-picture-input'), file)

    await waitFor(() => expect(screen.getByLabelText(/change profile photo/i).querySelector('img')).toHaveAttribute('src', '/media/profile-pictures/new.png'))
    expect(screen.getByRole('button', { name: /remove/i })).toBeInTheDocument()
  })

  test('a rejected upload (e.g. oversized file) shows the server error instead of the picture changing', async () => {
    const user = userEvent.setup()
    mockProfileLoad({ first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: null })
    renderWithAuth(<ProfilePage />)
    await waitFor(() => expect(screen.getByLabelText(/upload a profile photo/i)).toBeInTheDocument())

    const error = new Error('Something went wrong.')
    error.status = 400
    error.errors = { profile_picture: ['Image must be smaller than 2MB.'] }
    vi.mocked(realApi).mockImplementationOnce(async () => { throw error })

    const file = new File(['pixel'], 'too-big.png', { type: 'image/png' })
    await user.upload(screen.getByTestId('profile-picture-input'), file)

    await waitFor(() => expect(screen.getByText('Image must be smaller than 2MB.')).toBeInTheDocument())
    expect(screen.getByLabelText(/upload a profile photo/i).querySelector('img')).toBeNull()
  })

  test('removing a picture reverts the avatar to initials and hides the remove option', async () => {
    const user = userEvent.setup()
    mockProfileLoad({ first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: '/media/profile-pictures/old.png' })
    renderWithAuth(<ProfilePage />)

    await waitFor(() => expect(screen.getByLabelText(/change profile photo/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /remove/i })).toBeInTheDocument()

    vi.mocked(realApi).mockImplementationOnce(async (path, options) => {
      expect(path).toBe('/profile/picture/')
      expect(options.method).toBe('DELETE')
      return { user: { first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: null } }
    })
    vi.mocked(realApi).mockImplementationOnce(async (path) => {
      if (path === '/profile/') return { user: { first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: null } }
      throw new Error(`unexpected call to api(${path})`)
    })

    await user.click(screen.getByRole('button', { name: /remove/i }))

    await waitFor(() => expect(screen.getByLabelText(/upload a profile photo/i)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
  })
})

describe('Edit Profile page copy', () => {
  test('the email field has no standing "Can’t be changed" hint text (the disabled styling already shows that)', async () => {
    mockProfileLoadHelper()
    renderWithAuth(<ProfilePage />)
    await waitFor(() => expect(screen.getByDisplayValue('sanchu@nyu.edu')).toBeInTheDocument())
    expect(screen.queryByText(/can.t be changed/i)).not.toBeInTheDocument()
    expect(screen.getByDisplayValue('sanchu@nyu.edu')).toBeDisabled()
  })

  test('the password row shows a masked placeholder instead of the old instructional sentence', async () => {
    mockProfileLoadHelper()
    renderWithAuth(<ProfilePage />)
    await waitFor(() => expect(screen.getByText('••••••••••')).toBeInTheDocument())
    expect(screen.queryByText(/stay signed in/i)).not.toBeInTheDocument()
  })

  function mockProfileLoadHelper() {
    vi.mocked(realApi).mockImplementation(async (path) => {
      if (path === '/profile/') return { user: { first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: null } }
      throw new Error(`unexpected call to api(${path})`)
    })
  }
})

describe('study session reminders on the dashboard', () => {
  const reminder = {
    id: 5,
    starts_at: '2026-11-04T15:00:00+00:00',
    ends_at: '2026-11-04T16:00:00+00:00',
    assignment: { id: 2, title: 'Essay draft' },
    course: { id: 1, name: 'Writing', code: 'EXPOS 101' },
  }

  function dashboardWith(study_reminders) {
    return {
      user: { email: 'sam@nyu.edu' },
      metrics: { courses: 0, due_this_week: 0, overdue: 0 },
      courses: [],
      assignments: [],
      upcoming: [],
      study_reminders,
    }
  }

  function renderDashboard() {
    return render(<MemoryRouter><Dashboard /></MemoryRouter>)
  }

  async function refreshDashboard() {
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
  }

  afterEach(() => {
    vi.useRealTimers()
    localStorage.clear()
  })

  test('names the course, assignment and session time', async () => {
    vi.mocked(realApi).mockResolvedValue(dashboardWith([reminder]))
    renderDashboard()
    const alert = await screen.findByRole('status')
    expect(alert).toHaveTextContent('EXPOS 101 Writing · Essay draft starts Nov 4, 3:00 PM UTC')
  })

  test('shows nothing when no session is coming up', async () => {
    vi.mocked(realApi).mockResolvedValue(dashboardWith([]))
    renderDashboard()
    await screen.findByText('Everything is clear')
    expect(screen.queryByRole('status')).toBeNull()
  })

  test('appears and clears while the page stays open', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    vi.mocked(realApi).mockResolvedValue(dashboardWith([]))
    renderDashboard()
    await screen.findByText('Everything is clear')

    vi.mocked(realApi).mockResolvedValue(dashboardWith([reminder]))
    await refreshDashboard()
    expect(screen.getByRole('status')).toHaveTextContent('Essay draft')

    vi.mocked(realApi).mockResolvedValue(dashboardWith([]))
    await refreshDashboard()
    expect(screen.queryByRole('status')).toBeNull()
  })

  test('a failed refresh leaves the dashboard on screen', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    vi.mocked(realApi).mockResolvedValue(dashboardWith([reminder]))
    renderDashboard()
    await screen.findByRole('status')

    vi.mocked(realApi).mockRejectedValue(new Error('Network error'))
    await refreshDashboard()
    expect(screen.getByRole('status')).toHaveTextContent('Essay draft')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  test('dismissing sends no request and stays dismissed after a reload', async () => {
    vi.mocked(realApi).mockResolvedValue(dashboardWith([reminder]))
    const { unmount } = renderDashboard()
    await screen.findByRole('status')
    const callsBefore = vi.mocked(realApi).mock.calls.length

    await userEvent.click(screen.getByRole('button', { name: 'Dismiss reminder for EXPOS 101 Writing' }))
    expect(screen.queryByRole('status')).toBeNull()
    expect(vi.mocked(realApi).mock.calls.length).toBe(callsBefore)

    unmount()
    renderDashboard()
    await screen.findByText('Everything is clear')
    expect(screen.queryByRole('status')).toBeNull()
  })

  test('a dismissed session reminds again if it moves to a new time', async () => {
    vi.mocked(realApi).mockResolvedValue(dashboardWith([reminder]))
    const { unmount } = renderDashboard()
    await screen.findByRole('status')
    await userEvent.click(screen.getByRole('button', { name: /dismiss reminder/i }))
    unmount()

    vi.mocked(realApi).mockResolvedValue(dashboardWith([{ ...reminder, starts_at: '2026-11-04T15:30:00+00:00' }]))
    renderDashboard()
    expect(await screen.findByRole('status')).toHaveTextContent('3:30 PM UTC')
  })

  test('dismissing one reminder leaves the others', async () => {
    const other = { ...reminder, id: 6, course: { id: 3, name: 'Algorithms', code: '' } }
    vi.mocked(realApi).mockResolvedValue(dashboardWith([reminder, other]))
    renderDashboard()
    await screen.findAllByRole('status')
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss reminder for EXPOS 101 Writing' }))
    expect(screen.getByRole('status')).toHaveTextContent('Algorithms · Essay draft')
  })

  test('still works when browser storage is unavailable', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    vi.mocked(realApi).mockResolvedValue(dashboardWith([reminder]))
    renderDashboard()
    await screen.findByRole('status')
    await userEvent.click(screen.getByRole('button', { name: /dismiss reminder/i }))
    expect(screen.queryByRole('status')).toBeNull()
    setItem.mockRestore()
  })
})

describe('bio on the Edit Profile page', () => {
  function mockProfile(user) {
    vi.mocked(realApi).mockImplementation(async (path) => {
      if (path === '/profile/') return { user }
      throw new Error(`unexpected call to api(${path})`)
    })
  }

  test('shows the saved bio with a live character count', async () => {
    const user = userEvent.setup()
    mockProfile({ first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: null, bio: 'Hi' })
    renderWithAuth(<ProfilePage />)

    const bio = await screen.findByLabelText(/bio/i)
    expect(bio).toHaveValue('Hi')
    expect(screen.getByText('2 / 300')).toBeInTheDocument()

    await user.type(bio, ' there')
    expect(screen.getByText('8 / 300')).toBeInTheDocument()
  })

  test('a rejected bio shows the server error under the field', async () => {
    const user = userEvent.setup()
    mockProfile({ first_name: 'Sanchu', last_name: 'Kavitha Babu', email: 'sanchu@nyu.edu', profile_picture: null, bio: '' })
    renderWithAuth(<ProfilePage />)
    await screen.findByLabelText(/bio/i)

    const error = new Error('Something went wrong.')
    error.status = 400
    error.errors = { bio: ['Bio must be 300 characters or fewer.'] }
    vi.mocked(realApi).mockImplementationOnce(async () => { throw error })

    await user.click(screen.getByRole('button', { name: /save changes/i }))
    expect(await screen.findByText('Bio must be 300 characters or fewer.')).toBeInTheDocument()
  })
})
