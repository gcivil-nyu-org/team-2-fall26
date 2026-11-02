import { afterEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { api as realApi } from './api'
import { AppShell, AuthContext, ProfilePage } from './App'

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
