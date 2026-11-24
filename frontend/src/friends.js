// First/last name are optional (nothing requires a profile to be filled in
// before you can add a friend), so every display helper here falls back to the
// email. A student can also hide their email from others (#31), in which case
// the API sends it as null and the fallback is a generic label instead.
export function displayName(user) {
  if (!user) return ''
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ')
  return name || user.email || 'SemesterPilot student'
}

export function initial(user) {
  return (user?.first_name?.[0] || user?.email?.[0] || '?').toUpperCase()
}
