import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import {
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock3,
  GraduationCap,
  LayoutDashboard,
  LogOut,
  Menu,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'

import { api, formatDate, toUTCInput } from './api'
import { AvailabilityPage, CalendarPage } from './StudyPages'

const AuthContext = createContext(null)

function useAuth() {
  return useContext(AuthContext)
}

function AuthProvider({ children }) {
  const [session, setSession] = useState({ loading: true, authenticated: false, user: null })

  async function refresh() {
    try {
      const data = await api('/session/')
      setSession({ loading: false, ...data })
      return data
    } catch {
      setSession({ loading: false, authenticated: false, user: null })
      return null
    }
  }

  useEffect(() => { refresh() }, [])

  const value = useMemo(() => ({ session, refresh, setSession }), [session])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

function Logo({ light = false }) {
  return (
    <span className={`logo ${light ? 'logo--light' : ''}`}>
      <span className="logo__mark"><GraduationCap size={21} strokeWidth={2.1} /></span>
      <span>SemesterPilot</span>
    </span>
  )
}

function LoadingScreen() {
  return (
    <div className="loading-screen">
      <Logo />
      <span className="spinner" aria-label="Loading" />
    </div>
  )
}

function ProtectedRoute({ children }) {
  const { session } = useAuth()
  const location = useLocation()
  if (session.loading) return <LoadingScreen />
  if (!session.authenticated) return <Navigate to="/login" state={{ from: location }} replace />
  return children
}

function GuestRoute({ children }) {
  const { session } = useAuth()
  if (session.loading) return <LoadingScreen />
  if (session.authenticated) return <Navigate to="/dashboard" replace />
  return children
}

const navItems = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { to: '/calendar', label: 'Study calendar', icon: CalendarDays },
  { to: '/availability', label: 'Availability', icon: Clock3 },
  { to: '/completed', label: 'Completed', icon: CheckCircle2 },
]

function AppShell({ children }) {
  const { session, setSession } = useAuth()
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)

  async function logout() {
    await api('/auth/logout/', { method: 'POST', body: {} })
    setSession({ loading: false, authenticated: false, user: null })
    navigate('/login')
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar__top">
          <Logo />
          <button className="icon-button sidebar__close" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={20} /></button>
        </div>
        <p className="sidebar__label">Workspace</p>
        <nav className="sidebar__nav">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} onClick={() => setMobileOpen(false)} className={({ isActive }) => `nav-item ${isActive ? 'nav-item--active' : ''}`}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__spacer" />
        <div className="sidebar__profile">
          <NavLink to="/profile" onClick={() => setMobileOpen(false)} className="sidebar__profile-link" aria-label="Edit your profile">
            <div className="avatar">{(session.user?.first_name?.[0] || session.user?.email?.[0] || '?').toUpperCase()}</div>
            <div className="sidebar__identity">
              <strong>{[session.user?.first_name, session.user?.last_name].filter(Boolean).join(' ') || 'Student'}</strong>
              <span>{session.user?.email}</span>
            </div>
          </NavLink>
          <button className="icon-button" onClick={logout} aria-label="Log out"><LogOut size={17} /></button>
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-scrim" onClick={() => setMobileOpen(false)} aria-label="Close navigation" />}
      <div className="app-main">
        <header className="mobile-header">
          <button className="icon-button" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={22} /></button>
          <Logo />
          <span className="mobile-header__balance" />
        </header>
        <main className="page">{children}</main>
      </div>
    </div>
  )
}

function AuthVisual() {
  return (
    <section className="auth-visual">
      <Logo light />
      <div className="auth-visual__content">
        <div className="auth-orbit auth-orbit--one" />
        <div className="auth-orbit auth-orbit--two" />
        <div className="auth-badge"><Sparkles size={16} /> Built for focused semesters</div>
        <h1>Stay ahead.<br />Stay balanced.</h1>
        <p>Courses, deadlines, and the work that matters—all in one calm, clear place.</p>
        <div className="auth-preview" aria-hidden="true">
          <div className="auth-preview__top"><span>Today</span><span className="auth-preview__pill">3 on track</span></div>
          <div className="auth-preview__item"><span className="preview-dot preview-dot--violet" /><span><strong>Design critique</strong><small>Human-centered design</small></span><span>10:30</span></div>
          <div className="auth-preview__item"><span className="preview-dot preview-dot--orange" /><span><strong>Problem set 4</strong><small>Algorithms</small></span><span>17:00</span></div>
        </div>
      </div>
      <p className="auth-quote">“A clearer view of the week changes everything.”</p>
    </section>
  )
}

function AuthLayout({ mode }) {
  const isLogin = mode === 'login'
  const navigate = useNavigate()
  const location = useLocation()
  const { refresh } = useAuth()
  const [values, setValues] = useState({ email: '', password: '', password_confirm: '' })
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)

  function update(event) {
    setValues((current) => ({ ...current, [event.target.name]: event.target.value }))
    setErrors((current) => ({ ...current, [event.target.name]: undefined, non_field_errors: undefined }))
  }

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      await api(isLogin ? '/auth/login/' : '/auth/signup/', { method: 'POST', body: values })
      await refresh()
      navigate(location.state?.from?.pathname || '/dashboard', { replace: true })
    } catch (error) {
      setErrors(error.errors || { non_field_errors: [error.message] })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <AuthVisual />
      <section className="auth-panel">
        <div className="auth-panel__mobile-logo"><Logo /></div>
        <div className="auth-card">
          <p className="kicker">{isLogin ? 'Welcome back' : 'Start fresh'}</p>
          <h2>{isLogin ? 'Sign in to your workspace' : 'Create your account'}</h2>
          <p className="auth-card__intro">{isLogin ? 'Pick up where you left off.' : 'Your semester gets easier from here.'}</p>
          {errors.non_field_errors && <div className="form-alert">{errors.non_field_errors[0]}</div>}
          <form onSubmit={submit} className="form-stack">
            <Field label="Email address" error={errors.email?.[0]}>
              <input name="email" type="email" autoComplete="email" placeholder="you@nyu.edu" value={values.email} onChange={update} autoFocus required />
            </Field>
            <Field label="Password" error={errors.password?.[0] || errors.password1?.[0]}>
              <input name="password" type="password" autoComplete={isLogin ? 'current-password' : 'new-password'} placeholder={isLogin ? 'Enter your password' : 'At least 8 characters'} value={values.password} onChange={update} required />
            </Field>
            {!isLogin && (
              <Field label="Confirm password" error={errors.password_confirm?.[0] || errors.password2?.[0]}>
                <input name="password_confirm" type="password" autoComplete="new-password" placeholder="Enter it once more" value={values.password_confirm} onChange={update} required />
              </Field>
            )}
            {isLogin && (
              <p className="auth-forgot"><NavLink to="/forgot-password">Forgot your password?</NavLink></p>
            )}
            <button className="button button--primary button--wide" disabled={submitting}>
              {submitting ? <span className="spinner spinner--light" /> : <>{isLogin ? 'Sign in' : 'Create account'} <ArrowRight size={17} /></>}
            </button>
          </form>
          <p className="auth-switch">
            {isLogin ? 'New to SemesterPilot?' : 'Already have an account?'}{' '}
            <NavLink to={isLogin ? '/signup' : '/login'}>{isLogin ? 'Create an account' : 'Sign in'}</NavLink>
          </p>
        </div>
      </section>
    </div>
  )
}

function ForgotPassword() {
  const { session } = useAuth()
  const [email, setEmail] = useState(session.user?.email || '')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await api('/auth/password-reset/', { method: 'POST', body: { email } })
      setSent(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <AuthVisual />
      <section className="auth-panel">
        <div className="auth-panel__mobile-logo"><Logo /></div>
        <div className="auth-card">
          <p className="kicker">Reset your password</p>
          <h2>Forgot your password?</h2>
          <p className="auth-card__intro">Enter your NYU email and we’ll send you a link to reset it.</p>
          {sent ? (
            <div className="form-alert form-alert--success">If an account exists for that email, a reset link is on its way.</div>
          ) : (
            <form onSubmit={submit} className="form-stack">
              {error && <div className="form-alert">{error}</div>}
              <Field label="Email address">
                <input type="email" autoComplete="email" placeholder="you@nyu.edu" value={email} onChange={(event) => setEmail(event.target.value)} autoFocus required />
              </Field>
              <button className="button button--primary button--wide" disabled={submitting}>
                {submitting ? <span className="spinner spinner--light" /> : <>Send reset link <ArrowRight size={17} /></>}
              </button>
            </form>
          )}
          <p className="auth-switch">Remembered it? <NavLink to="/login">Sign in</NavLink></p>
        </div>
      </section>
    </div>
  )
}

function ResetPassword() {
  const { uid, token } = useParams()
  const navigate = useNavigate()
  const [values, setValues] = useState({ password: '', password_confirm: '' })
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  function update(event) {
    setValues((current) => ({ ...current, [event.target.name]: event.target.value }))
    setErrors((current) => ({ ...current, [event.target.name]: undefined, detail: undefined }))
  }

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      await api('/auth/password-reset/confirm/', { method: 'POST', body: { uid, token, ...values } })
      setDone(true)
    } catch (error) {
      setErrors(error.errors && (error.errors.password || error.errors.password_confirm) ? error.errors : { detail: [error.message] })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <AuthVisual />
      <section className="auth-panel">
        <div className="auth-panel__mobile-logo"><Logo /></div>
        <div className="auth-card">
          <p className="kicker">Almost there</p>
          <h2>Choose a new password</h2>
          {done ? (
            <>
              <div className="form-alert form-alert--success">Your password has been reset.</div>
              <button className="button button--primary button--wide" onClick={() => navigate('/login')}>Sign in <ArrowRight size={17} /></button>
            </>
          ) : (
            <form onSubmit={submit} className="form-stack">
              {errors.detail && (
                <div className="form-alert">
                  {errors.detail[0]} <NavLink to="/forgot-password">Request a new link</NavLink>.
                </div>
              )}
              <Field label="New password" error={errors.password?.[0]}>
                <input name="password" type="password" autoComplete="new-password" placeholder="At least 8 characters" value={values.password} onChange={update} autoFocus required />
              </Field>
              <Field label="Confirm new password" error={errors.password_confirm?.[0]}>
                <input name="password_confirm" type="password" autoComplete="new-password" placeholder="Enter it once more" value={values.password_confirm} onChange={update} required />
              </Field>
              <button className="button button--primary button--wide" disabled={submitting}>
                {submitting ? <span className="spinner spinner--light" /> : <>Reset password <ArrowRight size={17} /></>}
              </button>
            </form>
          )}
        </div>
      </section>
    </div>
  )
}

function Field({ label, hint, error, children }) {
  return (
    <label className={`field ${error ? 'field--error' : ''}`}>
      <span className="field__label">{label}{hint && <small>{hint}</small>}</span>
      {children}
      {error && <span className="field__error">{error}</span>}
    </label>
  )
}

function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="kicker">{eyebrow}</p>}
        <h1>{title}</h1>
        {subtitle && <p className="page-header__subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  )
}

function StatCard({ label, value, icon: Icon, tone, detail }) {
  return (
    <article className={`stat-card stat-card--${tone}`}>
      <div className="stat-card__icon"><Icon size={21} /></div>
      <div>
        <span className="stat-card__label">{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </article>
  )
}

function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  async function load() {
    try { setData(await api('/dashboard/')) } catch (err) { setError(err.message) }
  }

  useEffect(() => { load() }, [])

  if (!data && !error) return <PageSkeleton />
  if (error) return <ErrorState message={error} onRetry={load} />

  const filteredCourses = data.courses.filter((course) =>
    `${course.name} ${course.code}`.toLowerCase().includes(search.toLowerCase()),
  )
  const firstName = data.user.email.split('@')[0].split(/[._-]/)[0]

  return (
    <>
      <PageHeader
        eyebrow="Your workspace"
        title={`Good ${timeGreeting()}, ${capitalize(firstName)}`}
        subtitle="Here’s what deserves your attention today."
        actions={<NavLink className="button button--primary" to="/courses/new"><Plus size={17} /> Add course</NavLink>}
      />
      <section className="stats-grid" aria-label="Semester summary">
        <StatCard label="Active courses" value={data.metrics.courses} detail="this semester" icon={BookOpen} tone="violet" />
        <StatCard label="Due this week" value={data.metrics.due_this_week} detail="next 7 days" icon={CalendarDays} tone="green" />
        <StatCard label="Overdue" value={data.metrics.overdue} detail={data.metrics.overdue ? 'needs attention' : 'you’re all clear'} icon={Clock3} tone="orange" />
      </section>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel__header">
            <div><p className="kicker">Courses</p><h2>My semester</h2></div>
            {data.courses.length > 2 && <label className="search-box"><Search size={16} /><input aria-label="Search courses" placeholder="Search" value={search} onChange={(event) => setSearch(event.target.value)} /></label>}
          </div>
          {filteredCourses.length ? (
            <div className="course-list">
              {filteredCourses.map((course, index) => <CourseRow key={course.id} course={course} index={index} />)}
            </div>
          ) : (
            <EmptyState icon={BookOpen} title={data.courses.length ? 'No matching courses' : 'Your semester starts here'} body={data.courses.length ? 'Try a different search.' : 'Add your first course, then bring in assignments as they arrive.'} action={!data.courses.length && <NavLink className="button button--soft" to="/courses/new"><Plus size={16} /> Add a course</NavLink>} />
          )}
        </section>
        <section className="panel">
          <div className="panel__header">
            <div><p className="kicker">Focus queue</p><h2>Up next</h2></div>
            <NavLink className="text-link" to="/completed">Completed <ArrowRight size={14} /></NavLink>
          </div>
          {data.upcoming.length ? (
            <div className="assignment-list">
              {data.upcoming.slice(0, 6).map((item) => (
                item.kind === 'exam'
                  ? <ExamRow key={`exam-${item.id}`} exam={item} />
                  : <AssignmentRow key={`assignment-${item.id}`} assignment={item} onChange={load} compact />
              ))}
            </div>
          ) : (
            <EmptyState icon={CheckCircle2} title="Everything is clear" body="No outstanding assignments or upcoming exams. Enjoy the breathing room." />
          )}
        </section>
      </div>
    </>
  )
}

function CourseRow({ course, index }) {
  const colors = ['violet', 'blue', 'green', 'orange']
  return (
    <NavLink to={`/courses/${course.id}`} className="course-row">
      <span className={`course-row__mark course-row__mark--${colors[index % colors.length]}`}>{course.name.slice(0, 2).toUpperCase()}</span>
      <span className="course-row__copy">
        <strong>{course.name}</strong>
        <small>{course.code || 'No course code'} · {course.semester}</small>
      </span>
      <span className="course-row__count">{course.assignment_count} task{course.assignment_count === 1 ? '' : 's'}</span>
      <ChevronRight size={18} className="muted-icon" />
    </NavLink>
  )
}

function AssignmentRow({ assignment, onChange, compact = false, completed = false, deletable = false }) {
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  async function toggle() {
    setBusy(true)
    try {
      await api(`/assignments/${assignment.id}/`, {
        method: 'PATCH',
        body: { status: completed || assignment.status === 'complete' ? 'incomplete' : 'complete' },
      })
      await onChange?.()
    } finally { setBusy(false) }
  }

  async function remove() {
    setBusy(true)
    setDeleteError('')
    try {
      await api(`/assignments/${assignment.id}/`, { method: 'DELETE' })
      await onChange?.()
    } catch {
      setDeleteError('Couldn’t delete. Try again.')
    } finally { setBusy(false) }
  }

  function cancelDelete() {
    setConfirming(false)
    setDeleteError('')
  }

  const actions = (
    <>
      {!completed && <NavLink className="icon-button" to={`/assignments/${assignment.id}/edit`} aria-label={`Edit ${assignment.title}`}><Pencil size={15} /></NavLink>}
      {completed && <button className="button button--ghost button--small" onClick={toggle} disabled={busy}>Reopen</button>}
    </>
  )

  return (
    <div className={`assignment-row ${assignment.is_overdue ? 'assignment-row--overdue' : ''}`}>
      <button className={`complete-button ${assignment.status === 'complete' ? 'complete-button--done' : ''}`} onClick={toggle} disabled={busy} aria-label={assignment.status === 'complete' ? `Reopen ${assignment.title}` : `Complete ${assignment.title}`}>
        {assignment.status === 'complete' ? <Check size={15} /> : <Circle size={18} />}
      </button>
      <div className="assignment-row__copy">
        <strong>{assignment.title}</strong>
        <small>{assignment.course.name}{assignment.description && !compact ? ` · ${assignment.description}` : ''}</small>
      </div>
      <div className="assignment-row__date">
        {assignment.is_overdue && <span className="status-pill status-pill--danger">Overdue</span>}
        <span>{formatDate(assignment.due_date)}</span>
      </div>
      {!deletable && actions}
      {deletable && (
        <div className={`assignment-row__actions ${confirming ? 'assignment-row__actions--confirm' : ''}`}>
          {confirming ? (
            <>
              <span role="alert" className={deleteError ? 'assignment-row__error' : ''}>{deleteError || `Delete “${assignment.title}”?`}</span>
              <button className="button button--danger button--small" onClick={remove} disabled={busy}>Delete</button>
              <button className="button button--secondary button--small" onClick={cancelDelete} disabled={busy} autoFocus>Cancel</button>
            </>
          ) : (
            <>
              {actions}
              <button className="icon-button" onClick={() => setConfirming(true)} aria-label={`Delete ${assignment.title}`}><Trash2 size={15} /></button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function ExamRow({ exam }) {
  return (
    <div className="assignment-row">
      <span className="exam-mark" aria-hidden="true"><GraduationCap size={16} /></span>
      <div className="assignment-row__copy">
        <strong>{exam.title}</strong>
        <small>{exam.course.name}{exam.location ? ` · ${exam.location}` : ''}</small>
      </div>
      <div className="assignment-row__date">
        <span className="status-pill status-pill--exam">Exam</span>
        <span>{formatDate(exam.starts_at)}</span>
      </div>
    </div>
  )
}

function CourseDetail() {
  const { courseId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  async function load() {
    try { setData(await api(`/courses/${courseId}/`)) } catch (err) { setError(err.message) }
  }
  async function remove() {
    setDeleting(true)
    setDeleteError('')
    try {
      await api(`/courses/${courseId}/`, { method: 'DELETE' })
      navigate('/dashboard')
    } catch {
      setDeleteError('Couldn’t delete this course. Try again.')
      setDeleting(false)
    }
  }
  function cancelDelete() {
    setConfirming(false)
    setDeleteError('')
  }
  useEffect(() => { load() }, [courseId])
  if (!data && !error) return <PageSkeleton />
  if (error) return <ErrorState message={error} onRetry={load} />
  const { course } = data
  const open = course.assignments.filter((item) => item.status === 'incomplete')
  const complete = course.assignments.filter((item) => item.status === 'complete')
  return (
    <>
      <NavLink className="back-link" to="/dashboard"><ArrowLeft size={16} /> Back to overview</NavLink>
      <PageHeader
        eyebrow={course.code || 'Course'}
        title={course.name}
        subtitle={course.semester}
        actions={<><button className="button button--secondary" onClick={() => setConfirming(true)} disabled={confirming}><Trash2 size={16} /> Delete course</button><NavLink className="button button--secondary" to={`/courses/${course.id}/edit`}><Pencil size={16} /> Edit course</NavLink><NavLink className="button button--primary" to={`/courses/${course.id}/assignments/new`}><Plus size={17} /> Add assignment</NavLink></>}
      />
      {confirming && (
        <div className="delete-confirm" role="alert">
          <p className={deleteError ? 'delete-confirm__error' : ''}>
            {deleteError || (course.assignments.length
              ? `Delete “${course.name}” and its ${course.assignments.length} assignment${course.assignments.length === 1 ? '' : 's'}? This can’t be undone.`
              : `Delete “${course.name}”? This can’t be undone.`)}
          </p>
          <div>
            <button className="button button--danger button--small" onClick={remove} disabled={deleting}>Delete course</button>
            <button className="button button--secondary button--small" onClick={cancelDelete} disabled={deleting} autoFocus>Cancel</button>
          </div>
        </div>
      )}
      <div className="course-hero">
        <div><span>Open work</span><strong>{open.length}</strong></div>
        <div><span>Completed</span><strong>{complete.length}</strong></div>
        <div><span>Progress</span><strong>{course.assignments.length ? Math.round((complete.length / course.assignments.length) * 100) : 0}%</strong></div>
        <div className="progress-ring" style={{ '--progress': `${course.assignments.length ? Math.round((complete.length / course.assignments.length) * 100) : 0}%` }}><Check size={21} /></div>
      </div>
      <section className="panel panel--full">
        <div className="panel__header"><div><p className="kicker">Assignments</p><h2>Course work</h2></div><span className="count-pill">{open.length} open</span></div>
        {course.assignments.length ? (
          <div className="assignment-list">
            {open.map((assignment) => <AssignmentRow key={assignment.id} assignment={assignment} onChange={load} deletable />)}
            {complete.length > 0 && <div className="completed-divider"><span>Completed</span></div>}
            {complete.map((assignment) => <AssignmentRow key={assignment.id} assignment={assignment} onChange={load} completed deletable />)}
          </div>
        ) : (
          <EmptyState icon={CalendarDays} title="Nothing assigned yet" body="Add the first assignment for this course when you’re ready." action={<NavLink className="button button--soft" to={`/courses/${course.id}/assignments/new`}><Plus size={16} /> Add assignment</NavLink>} />
        )}
      </section>
      <section className="panel panel--full panel--stacked">
        <div className="panel__header">
          <div><p className="kicker">Exams</p><h2>Exam schedule</h2></div>
          <NavLink className="button button--soft button--small" to={`/courses/${course.id}/exams/new`}><Plus size={15} /> Add exam</NavLink>
        </div>
        {course.exams.length ? (
          <div className="assignment-list">
            {course.exams.map((exam) => <ExamRow key={exam.id} exam={exam} />)}
          </div>
        ) : (
          <EmptyState icon={GraduationCap} title="No exams yet" body="Add midterms and finals here so you can plan your prep." />
        )}
      </section>
    </>
  )
}

function CourseFormPage({ editing = false }) {
  const { courseId } = useParams()
  const navigate = useNavigate()
  const [semester, setSemester] = useState(null)
  const [values, setValues] = useState({ name: '', code: '', semester: '' })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [loadAttempt, setLoadAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    async function load() {
      try {
        const data = editing ? await api(`/courses/${courseId}/`) : await api('/courses/')
        if (!active) return
        setSemester(data.semester)
        setValues(editing ? {
          name: data.course.name,
          code: data.course.code,
          semester: data.course.semester,
        } : { name: '', code: '', semester: data.semester.default })
      } catch (error) {
        if (active) setLoadError(error.status === 401 ? 'Your session expired. Please sign in again.' : 'We couldn’t load this course. Check the link or try again.')
      } finally { if (active) setLoading(false) }
    }
    load()
    return () => { active = false }
  }, [editing, courseId, loadAttempt])

  function update(event) {
    setValues((current) => ({ ...current, [event.target.name]: event.target.value }))
    setErrors((current) => ({ ...current, [event.target.name]: undefined }))
  }

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      const result = await api(editing ? `/courses/${courseId}/` : '/courses/', {
        method: editing ? 'PUT' : 'POST', body: values,
      })
      navigate(`/courses/${result.course.id}`)
    } catch (error) { setErrors(error.errors || {}) } finally { setSubmitting(false) }
  }

  if (loading) return <PageSkeleton />
  if (loadError) return <ErrorState message={loadError} onRetry={() => setLoadAttempt((value) => value + 1)} />
  return (
    <FormPage
      backTo={editing ? `/courses/${courseId}` : '/dashboard'}
      eyebrow={editing ? 'Course settings' : 'Build your semester'}
      title={editing ? 'Edit course' : 'Add a course'}
      subtitle={editing ? 'Keep the details accurate and easy to scan.' : 'Give this course a home for every deadline and assignment.'}
    >
      <form onSubmit={submit} className="editor-card">
        <Field label="Course name" error={errors.name?.[0]}><input name="name" value={values.name} onChange={update} placeholder="e.g. Software Engineering" autoFocus required /></Field>
        <Field label="Course code" hint="Optional" error={errors.code?.[0]}><input name="code" value={values.code} onChange={update} aria-label="Course code" /></Field>
        <Field label="Semester" error={errors.semester?.[0]}>
          <select name="semester" value={values.semester} onChange={update} required>
            {semester?.choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
          </select>
        </Field>
        <FormActions submitting={submitting} label={editing ? 'Save changes' : 'Add course'} cancel={() => navigate(editing ? `/courses/${courseId}` : '/dashboard')} />
      </form>
    </FormPage>
  )
}

function ProfilePage() {
  const navigate = useNavigate()
  const { refresh } = useAuth()
  const [values, setValues] = useState({ first_name: '', last_name: '' })
  const [email, setEmail] = useState('')
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [passwordValues, setPasswordValues] = useState({ current_password: '', new_password: '', new_password_confirm: '' })
  const [passwordErrors, setPasswordErrors] = useState({})
  const [passwordSubmitting, setPasswordSubmitting] = useState(false)
  const [passwordSaved, setPasswordSaved] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    async function load() {
      try {
        const data = await api('/profile/')
        if (!active) return
        setValues({ first_name: data.user.first_name, last_name: data.user.last_name })
        setEmail(data.user.email)
      } catch (error) {
        if (active) setLoadError(error.status === 401 ? 'Your session expired. Please sign in again.' : 'We couldn’t load your profile. Try again.')
      } finally { if (active) setLoading(false) }
    }
    load()
    return () => { active = false }
  }, [loadAttempt])

  function update(event) {
    setValues((current) => ({ ...current, [event.target.name]: event.target.value }))
    setErrors((current) => ({ ...current, [event.target.name]: undefined }))
    setSaved(false)
  }

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      await api('/profile/', { method: 'PUT', body: values })
      await refresh()
      setSaved(true)
    } catch (error) { setErrors(error.errors || {}) } finally { setSubmitting(false) }
  }

  function updatePassword(event) {
    setPasswordValues((current) => ({ ...current, [event.target.name]: event.target.value }))
    setPasswordErrors((current) => ({ ...current, [event.target.name]: undefined, detail: undefined }))
  }

  function cancelPasswordEdit() {
    setPasswordOpen(false)
    setPasswordValues({ current_password: '', new_password: '', new_password_confirm: '' })
    setPasswordErrors({})
  }

  async function submitPassword(event) {
    event.preventDefault()
    setPasswordSubmitting(true)
    setPasswordErrors({})
    try {
      await api('/auth/change-password/', { method: 'POST', body: passwordValues })
      setPasswordValues({ current_password: '', new_password: '', new_password_confirm: '' })
      setPasswordOpen(false)
      setPasswordSaved(true)
    } catch (error) {
      setPasswordErrors(error.errors || { detail: [error.message] })
    } finally {
      setPasswordSubmitting(false)
    }
  }

  if (loading) return <PageSkeleton />
  if (loadError) return <ErrorState message={loadError} onRetry={() => setLoadAttempt((value) => value + 1)} />
  return (
    <FormPage backTo="/dashboard" eyebrow="Account" title="Edit profile" subtitle="Keep your name accurate so your work stays personal to you.">
      <form onSubmit={submit} className="editor-card">
        {saved && <div className="form-alert form-alert--success">Your profile has been updated.</div>}
        <Field label="First name" error={errors.first_name?.[0]}>
          <input name="first_name" value={values.first_name} onChange={update} autoFocus required />
        </Field>
        <Field label="Last name" error={errors.last_name?.[0]}>
          <input name="last_name" value={values.last_name} onChange={update} required />
        </Field>
        <Field label="Email" hint="Can't be changed">
          <input value={email} disabled />
        </Field>
        <FormActions submitting={submitting} label="Save changes" cancel={() => navigate('/dashboard')} />
      </form>
      <div className="editor-card">
        {passwordOpen ? (
          <form onSubmit={submitPassword} className="form-stack">
            <h3>Change password</h3>
            {passwordErrors.detail && <div className="form-alert">{passwordErrors.detail[0]}</div>}
            <Field label="Current password" error={passwordErrors.current_password?.[0]}>
              <input name="current_password" type="password" autoComplete="current-password" value={passwordValues.current_password} onChange={updatePassword} autoFocus required />
            </Field>
            <p className="auth-forgot"><NavLink to="/forgot-password">Forgot your current password?</NavLink></p>
            <Field label="New password" error={passwordErrors.new_password?.[0]}>
              <input name="new_password" type="password" autoComplete="new-password" placeholder="At least 8 characters" value={passwordValues.new_password} onChange={updatePassword} required />
            </Field>
            <Field label="Confirm new password" error={passwordErrors.new_password_confirm?.[0]}>
              <input name="new_password_confirm" type="password" autoComplete="new-password" value={passwordValues.new_password_confirm} onChange={updatePassword} required />
            </Field>
            <FormActions submitting={passwordSubmitting} label="Update password" cancel={cancelPasswordEdit} />
          </form>
        ) : (
          <div className="profile-security">
            <div>
              <h3>Password</h3>
              <p>{passwordSaved ? 'Your password has been updated.' : "Update your password without leaving this page \u2014 you'll stay signed in."}</p>
            </div>
            <button type="button" className="button button--secondary" onClick={() => setPasswordOpen(true)}>Change password</button>
          </div>
        )}
      </div>
    </FormPage>
  )
}

function AssignmentFormPage({ editing = false }) {
  const { courseId, assignmentId } = useParams()
  const navigate = useNavigate()
  const [course, setCourse] = useState(null)
  const [values, setValues] = useState({ title: '', due_date: '', description: '' })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [loadAttempt, setLoadAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    async function load() {
      try {
        if (editing) {
          const data = await api(`/assignments/${assignmentId}/`)
          if (!active) return
          setCourse(data.assignment.course)
          setValues({ title: data.assignment.title, due_date: toUTCInput(data.assignment.due_date), description: data.assignment.description })
        } else {
          const data = await api(`/courses/${courseId}/`)
          if (!active) return
          setCourse(data.course)
        }
      } catch (error) {
        if (active) setLoadError(error.status === 401 ? 'Your session expired. Please sign in again.' : 'We couldn’t load this assignment or course. Check the link or try again.')
      } finally { if (active) setLoading(false) }
    }
    load()
    return () => { active = false }
  }, [editing, assignmentId, courseId, loadAttempt])

  function update(event) {
    setValues((current) => ({ ...current, [event.target.name]: event.target.value }))
    setErrors((current) => ({ ...current, [event.target.name]: undefined }))
  }

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      await api(editing ? `/assignments/${assignmentId}/` : `/courses/${courseId}/assignments/`, {
        method: editing ? 'PUT' : 'POST', body: values,
      })
      navigate(`/courses/${course.id}`)
    } catch (error) { setErrors(error.errors || {}) } finally { setSubmitting(false) }
  }

  if (loading) return <PageSkeleton />
  if (loadError || !course) return <ErrorState message={loadError || 'This course could not be loaded.'} onRetry={() => setLoadAttempt((value) => value + 1)} />
  return (
    <FormPage
      backTo={`/courses/${course.id}`}
      eyebrow={editing ? 'Assignment details' : course.code || 'New assignment'}
      title={editing ? 'Edit assignment' : 'Add an assignment'}
      subtitle={`${course.name} · Keep the next step concrete.`}
    >
      <form onSubmit={submit} className="editor-card">
        <Field label="Assignment title" error={errors.title?.[0]}><input name="title" value={values.title} onChange={update} placeholder="e.g. Sprint retrospective" autoFocus required /></Field>
        <Field label="Deadline" hint="Time zone: UTC" error={errors.due_date?.[0]}><input name="due_date" type="datetime-local" value={values.due_date} onChange={update} onInput={update} required /></Field>
        <Field label="Description" hint="Optional" error={errors.description?.[0]}><textarea name="description" rows="4" value={values.description} onChange={update} placeholder="Add context, requirements, or a quick note…" /></Field>
        <FormActions submitting={submitting} label={editing ? 'Save changes' : 'Add assignment'} cancel={() => navigate(`/courses/${course.id}`)} />
      </form>
    </FormPage>
  )
}

function ExamFormPage() {
  const { courseId } = useParams()
  const navigate = useNavigate()
  const [course, setCourse] = useState(null)
  const [values, setValues] = useState({ title: '', starts_at: '', location: '' })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [loadAttempt, setLoadAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    async function load() {
      try {
        const data = await api(`/courses/${courseId}/`)
        if (active) setCourse(data.course)
      } catch (error) {
        if (active) setLoadError(error.status === 401 ? 'Your session expired. Please sign in again.' : 'We couldn’t load this course. Check the link or try again.')
      } finally { if (active) setLoading(false) }
    }
    load()
    return () => { active = false }
  }, [courseId, loadAttempt])

  function update(event) {
    setValues((current) => ({ ...current, [event.target.name]: event.target.value }))
    setErrors((current) => ({ ...current, [event.target.name]: undefined }))
  }

  async function submit(event) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      await api(`/courses/${courseId}/exams/`, { method: 'POST', body: values })
      navigate(`/courses/${course.id}`)
    } catch (error) { setErrors(error.errors || {}) } finally { setSubmitting(false) }
  }

  if (loading) return <PageSkeleton />
  if (loadError || !course) return <ErrorState message={loadError || 'This course could not be loaded.'} onRetry={() => setLoadAttempt((value) => value + 1)} />
  return (
    <FormPage
      backTo={`/courses/${course.id}`}
      eyebrow={course.code || 'New exam'}
      title="Add an exam"
      subtitle={`${course.name} · Know when and where it is.`}
    >
      <form onSubmit={submit} className="editor-card">
        <Field label="Exam title" error={errors.title?.[0]}><input name="title" value={values.title} onChange={update} placeholder="e.g. Midterm" autoFocus required /></Field>
        <Field label="Date and time" hint="Time zone: UTC" error={errors.starts_at?.[0]}><input name="starts_at" type="datetime-local" value={values.starts_at} onChange={update} onInput={update} required /></Field>
        <Field label="Location" hint="Optional" error={errors.location?.[0]}><input name="location" value={values.location} onChange={update} placeholder="e.g. 370 Jay St, Room 202" /></Field>
        <FormActions submitting={submitting} label="Add exam" cancel={() => navigate(`/courses/${course.id}`)} />
      </form>
    </FormPage>
  )
}

function FormPage({ backTo, eyebrow, title, subtitle, children }) {
  return (
    <div className="form-page">
      <NavLink className="back-link" to={backTo}><ArrowLeft size={16} /> Back</NavLink>
      <PageHeader eyebrow={eyebrow} title={title} subtitle={subtitle} />
      {children}
    </div>
  )
}

function FormActions({ submitting, label, cancel }) {
  return (
    <div className="form-actions">
      <button type="button" className="button button--secondary" onClick={cancel}>Cancel</button>
      <button className="button button--primary" disabled={submitting}>{submitting ? <span className="spinner spinner--light" /> : <>{label} <ArrowRight size={16} /></>}</button>
    </div>
  )
}

function Completed() {
  const [assignments, setAssignments] = useState(null)
  const [error, setError] = useState('')
  async function load() {
    try { setAssignments((await api('/assignments/?status=complete')).assignments) } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])
  if (!assignments && !error) return <PageSkeleton />
  if (error) return <ErrorState message={error} onRetry={load} />
  return (
    <>
      <PageHeader eyebrow="Progress archive" title="Completed work" subtitle="A record of everything you’ve moved across the finish line." />
      <section className="panel panel--full">
        <div className="panel__header"><div><p className="kicker">Finished</p><h2>Assignment history</h2></div><span className="count-pill">{assignments.length} total</span></div>
        {assignments.length ? <div className="assignment-list">{assignments.map((item) => <AssignmentRow key={item.id} assignment={item} onChange={load} completed />)}</div> : <EmptyState icon={CheckCircle2} title="Nothing completed yet" body="Finished assignments will collect here so you can always see your progress." />}
      </section>
    </>
  )
}

function EmptyState({ icon: Icon, title, body, action }) {
  return <div className="empty-state"><span><Icon size={23} /></span><h3>{title}</h3><p>{body}</p>{action}</div>
}

function ErrorState({ message, onRetry }) {
  return <div className="empty-state empty-state--page" role="alert"><span><X size={23} /></span><h3>We hit a snag</h3><p>{message}</p><button className="button button--soft" onClick={onRetry}>Try again</button><a className="text-link" href="/app/login">Go to sign in</a></div>
}

function PageSkeleton() {
  return <div className="skeleton-page"><div className="skeleton skeleton--small" /><div className="skeleton skeleton--title" /><div className="skeleton skeleton--line" /><div className="skeleton-grid"><div className="skeleton skeleton--card" /><div className="skeleton skeleton--card" /><div className="skeleton skeleton--card" /></div><div className="skeleton skeleton--panel" /></div>
}

function NotFound() {
  return <EmptyState icon={MoreHorizontal} title="This page wandered off" body="The page you’re looking for doesn’t exist." action={<NavLink className="button button--soft" to="/dashboard">Back to overview</NavLink>} />
}

function capitalize(value) { return value ? value[0].toUpperCase() + value.slice(1) : 'there' }
function timeGreeting() { const hour = new Date().getHours(); return hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening' }

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<GuestRoute><AuthLayout mode="login" /></GuestRoute>} />
      <Route path="/signup" element={<GuestRoute><AuthLayout mode="signup" /></GuestRoute>} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password/:uid/:token" element={<ResetPassword />} />
      <Route path="*" element={<ProtectedRoute><AppShell><Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/availability" element={<AvailabilityPage />} />
        <Route path="/courses/new" element={<CourseFormPage />} />
        <Route path="/courses/:courseId" element={<CourseDetail />} />
        <Route path="/courses/:courseId/edit" element={<CourseFormPage editing />} />
        <Route path="/courses/:courseId/assignments/new" element={<AssignmentFormPage />} />
        <Route path="/courses/:courseId/exams/new" element={<ExamFormPage />} />
        <Route path="/assignments/:assignmentId/edit" element={<AssignmentFormPage editing />} />
        <Route path="/completed" element={<Completed />} />
        <Route path="*" element={<NotFound />} />
      </Routes></AppShell></ProtectedRoute>} />
    </Routes>
  )
}

export default function App() {
  return <AuthProvider><AppRoutes /></AuthProvider>
}
