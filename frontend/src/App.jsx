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
  X,
} from 'lucide-react'

import { api, formatDate, toLocalInput } from './api'

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
          <div className="avatar">{session.user?.email?.[0]?.toUpperCase()}</div>
          <div className="sidebar__identity">
            <strong>Student</strong>
            <span>{session.user?.email}</span>
          </div>
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
          {data.assignments.length ? (
            <div className="assignment-list">
              {data.assignments.slice(0, 6).map((assignment) => (
                <AssignmentRow key={assignment.id} assignment={assignment} onChange={load} compact />
              ))}
            </div>
          ) : (
            <EmptyState icon={CheckCircle2} title="Everything is clear" body="No outstanding assignments. Enjoy the breathing room." />
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

function AssignmentRow({ assignment, onChange, compact = false, completed = false }) {
  const [busy, setBusy] = useState(false)

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
      {!completed && <NavLink className="icon-button" to={`/assignments/${assignment.id}/edit`} aria-label={`Edit ${assignment.title}`}><Pencil size={15} /></NavLink>}
      {completed && <button className="button button--ghost button--small" onClick={toggle} disabled={busy}>Reopen</button>}
    </div>
  )
}

function CourseDetail() {
  const { courseId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  async function load() {
    try { setData(await api(`/courses/${courseId}/`)) } catch (err) { setError(err.message) }
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
        actions={<><NavLink className="button button--secondary" to={`/courses/${course.id}/edit`}><Pencil size={16} /> Edit course</NavLink><NavLink className="button button--primary" to={`/courses/${course.id}/assignments/new`}><Plus size={17} /> Add assignment</NavLink></>}
      />
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
            {open.map((assignment) => <AssignmentRow key={assignment.id} assignment={assignment} onChange={load} />)}
            {complete.length > 0 && <div className="completed-divider"><span>Completed</span></div>}
            {complete.map((assignment) => <AssignmentRow key={assignment.id} assignment={assignment} onChange={load} completed />)}
          </div>
        ) : (
          <EmptyState icon={CalendarDays} title="Nothing assigned yet" body="Add the first assignment for this course when you’re ready." action={<NavLink className="button button--soft" to={`/courses/${course.id}/assignments/new`}><Plus size={16} /> Add assignment</NavLink>} />
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

  useEffect(() => {
    async function load() {
      try {
        const data = editing ? await api(`/courses/${courseId}/`) : await api('/courses/')
        setSemester(data.semester)
        setValues(editing ? {
          name: data.course.name,
          code: data.course.code,
          semester: data.course.semester,
        } : { name: '', code: '', semester: data.semester.default })
      } finally { setLoading(false) }
    }
    load()
  }, [editing, courseId])

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

function AssignmentFormPage({ editing = false }) {
  const { courseId, assignmentId } = useParams()
  const navigate = useNavigate()
  const [course, setCourse] = useState(null)
  const [values, setValues] = useState({ title: '', due_date: '', description: '' })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        if (editing) {
          const data = await api(`/assignments/${assignmentId}/`)
          setCourse(data.assignment.course)
          setValues({ title: data.assignment.title, due_date: toLocalInput(data.assignment.due_date), description: data.assignment.description })
        } else {
          const data = await api(`/courses/${courseId}/`)
          setCourse(data.course)
        }
      } finally { setLoading(false) }
    }
    load()
  }, [editing, assignmentId, courseId])

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
  return (
    <FormPage
      backTo={`/courses/${course.id}`}
      eyebrow={editing ? 'Assignment details' : course.code || 'New assignment'}
      title={editing ? 'Edit assignment' : 'Add an assignment'}
      subtitle={`${course.name} · Keep the next step concrete.`}
    >
      <form onSubmit={submit} className="editor-card">
        <Field label="Assignment title" error={errors.title?.[0]}><input name="title" value={values.title} onChange={update} placeholder="e.g. Sprint retrospective" autoFocus required /></Field>
        <Field label="Deadline" error={errors.due_date?.[0]}><input name="due_date" type="datetime-local" value={values.due_date} onChange={update} onInput={update} required /></Field>
        <Field label="Description" hint="Optional" error={errors.description?.[0]}><textarea name="description" rows="4" value={values.description} onChange={update} placeholder="Add context, requirements, or a quick note…" /></Field>
        <FormActions submitting={submitting} label={editing ? 'Save changes' : 'Add assignment'} cancel={() => navigate(`/courses/${course.id}`)} />
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
  return <div className="empty-state empty-state--page"><span><X size={23} /></span><h3>We hit a snag</h3><p>{message}</p><button className="button button--soft" onClick={onRetry}>Try again</button></div>
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
      <Route path="*" element={<ProtectedRoute><AppShell><Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/courses/new" element={<CourseFormPage />} />
        <Route path="/courses/:courseId" element={<CourseDetail />} />
        <Route path="/courses/:courseId/edit" element={<CourseFormPage editing />} />
        <Route path="/courses/:courseId/assignments/new" element={<AssignmentFormPage />} />
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
