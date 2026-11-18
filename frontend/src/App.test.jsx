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

describe('sidebar navigation', () => {
  test('links to the community food feed', () => {
    renderWithAuth(<AppShell>content</AppShell>)
    expect(screen.getByRole('link', { name: /community/i })).toHaveAttribute('href', '/community')
  })
})

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
    expect(alert).toHaveTextContent('EXPOS 101 Writing · Essay draft starts Nov 4, 10:00 AM EST')
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
    expect(await screen.findByRole('status')).toHaveTextContent('10:30 AM EST')
  })

  test('exam prep sessions are named after the exam', async () => {
    vi.mocked(realApi).mockResolvedValue(dashboardWith([{ ...reminder, assignment: null, exam: { id: 4, title: 'Midterm' } }]))
    renderDashboard()
    expect(await screen.findByRole('status')).toHaveTextContent('EXPOS 101 Writing · Midterm prep starts')
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

describe('due-date reminders on the dashboard (#37)', () => {
  const assignment = {
    id: 5, kind: 'assignment', title: 'Essay draft', when: '2026-11-04T15:00:00+00:00',
    course: { id: 1, name: 'Writing', code: 'EXPOS 101' },
  }
  const exam = {
    id: 8, kind: 'exam', title: 'Midterm', when: '2026-11-04T18:00:00+00:00',
    course: { id: 2, name: 'Calculus', code: '' },
  }

  function dashboardWith(deadline_reminders) {
    return {
      user: { email: 'sam@nyu.edu' },
      metrics: { courses: 0, due_this_week: 0, overdue: 0 },
      courses: [], assignments: [], upcoming: [],
      study_reminders: [],
      deadline_reminders,
    }
  }

  afterEach(() => localStorage.clear())

  test('names the course, the assignment and when it is due', async () => {
    vi.mocked(realApi).mockResolvedValue(dashboardWith([assignment]))
    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    const notice = await screen.findByRole('status')
    expect(notice).toHaveTextContent('Due soon')
    expect(notice).toHaveTextContent('EXPOS 101 Writing · Essay draft is due Nov 4, 10:00 AM EST')
  })

  test('an exam says it starts rather than is due, and copes with a course that has no code', async () => {
    vi.mocked(realApi).mockResolvedValue(dashboardWith([exam]))
    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    const notice = await screen.findByRole('status')
    expect(notice).toHaveTextContent('Exam soon')
    expect(notice).toHaveTextContent('Calculus · Midterm starts Nov 4, 1:00 PM EST')
  })

  test('lists each item once', async () => {
    vi.mocked(realApi).mockResolvedValue(dashboardWith([assignment, exam]))
    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    await screen.findByText('Due soon')
    expect(screen.getAllByRole('status')).toHaveLength(2)
  })

  test('shows nothing when nothing is coming up, or when the server sends no list at all', async () => {
    vi.mocked(realApi).mockResolvedValue(dashboardWith([]))
    const { unmount } = render(<MemoryRouter><Dashboard /></MemoryRouter>)
    await screen.findByText('Everything is clear')
    expect(screen.queryByRole('status')).toBeNull()
    unmount()

    const { deadline_reminders, ...withoutList } = dashboardWith([])
    vi.mocked(realApi).mockResolvedValue(withoutList)
    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    await screen.findByText('Everything is clear')
    expect(screen.queryByRole('status')).toBeNull()
  })

  test('dismissing hides it for good in this browser without calling the server', async () => {
    const user = userEvent.setup()
    vi.mocked(realApi).mockResolvedValue(dashboardWith([assignment, exam]))
    const { unmount } = render(<MemoryRouter><Dashboard /></MemoryRouter>)
    await screen.findByText('Due soon')
    const callsBefore = vi.mocked(realApi).mock.calls.length
    await user.click(screen.getByRole('button', { name: 'Dismiss reminder for Essay draft' }))
    expect(screen.queryByText('Due soon')).toBeNull()
    expect(screen.getByText('Exam soon')).toBeInTheDocument()
    expect(vi.mocked(realApi).mock.calls.length).toBe(callsBefore)
    unmount()

    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    await screen.findByText('Exam soon')
    expect(screen.queryByText('Due soon')).toBeNull()
  })

  test('an item moved to a new time reminds the student again', async () => {
    const user = userEvent.setup()
    vi.mocked(realApi).mockResolvedValue(dashboardWith([assignment]))
    const { unmount } = render(<MemoryRouter><Dashboard /></MemoryRouter>)
    await user.click(await screen.findByRole('button', { name: 'Dismiss reminder for Essay draft' }))
    unmount()

    vi.mocked(realApi).mockResolvedValue(dashboardWith([{ ...assignment, when: '2026-11-04T16:00:00+00:00' }]))
    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    expect(await screen.findByText('Due soon')).toBeInTheDocument()
  })

  test('an assignment and an exam with the same id are dismissed separately', async () => {
    const user = userEvent.setup()
    vi.mocked(realApi).mockResolvedValue(dashboardWith([{ ...assignment, id: 1 }, { ...exam, id: 1, when: assignment.when }]))
    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    await user.click(await screen.findByRole('button', { name: 'Dismiss reminder for Essay draft' }))
    expect(screen.getByText('Exam soon')).toBeInTheDocument()
  })

  test('still works when the browser will not store the dismissal', async () => {
    const user = userEvent.setup()
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    vi.mocked(realApi).mockResolvedValue(dashboardWith([assignment]))
    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    await user.click(await screen.findByRole('button', { name: 'Dismiss reminder for Essay draft' }))
    expect(screen.queryByText('Due soon')).toBeNull()
    setItem.mockRestore()
  })

  test('ignores a damaged dismissal list in storage', async () => {
    localStorage.setItem('dismissed-deadline-reminders', '{not json')
    vi.mocked(realApi).mockResolvedValue(dashboardWith([assignment]))
    render(<MemoryRouter><Dashboard /></MemoryRouter>)
    expect(await screen.findByText('Due soon')).toBeInTheDocument()
    localStorage.setItem('dismissed-deadline-reminders', '"a string"')
  })
})
