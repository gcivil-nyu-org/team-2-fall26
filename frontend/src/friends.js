// A student record from the API always has an email, but first/last name are
// optional (nothing requires a profile to be filled in before you can add a
// friend), so every display helper here falls back to the email.
export function displayName(user) {
  if (!user) return ''
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ')
  // A student can hide their email (#31), in which case the API sends null.
  return name || user.email || 'SemesterPilot student'
}

export function initial(user) {
  return (user?.first_name?.[0] || user?.email?.[0] || '?').toUpperCase()
}
