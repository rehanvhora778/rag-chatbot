/**
 * Central project config — EDIT THESE.
 *
 * Everything the college-facing landing page shows lives here so the whole
 * group can be updated in one place. Items marked TODO are placeholders.
 */
export const PROJECT = {
  name: 'RAG Chatbot',
  type: 'Project',
  college: 'L.J. University',
  department: 'AI & Data Science',      // TODO: your department / course name
  email: 'rehanvhora86@gmail.com',      // contact shown on legal pages
}

// Group members shown in the "Our Team" section — EDIT names, IDs and roles.
export const TEAM = [
  { name: 'Rayhan Vora', enrollment: 'Enrollment No. TODO', role: 'Backend & RAG Pipeline' },
  { name: 'Nikhil',      enrollment: 'Enrollment No. TODO', role: 'Frontend Development' },
  { name: 'Mansi',       enrollment: 'Enrollment No. TODO', role: 'Database, Testing & Documentation' },
]

// "Rayhan, Nikhil & Mansi" — used on the auth brand panel.
export const TEAM_NAMES = TEAM.map(m => m.name.split(' ')[0])
  .reduce((acc, n, i, arr) => (i === 0 ? n : i === arr.length - 1 ? `${acc} & ${n}` : `${acc}, ${n}`), '')

// Where "Launch Application" sends a logged-out visitor
export const APP_ENTRY = '/register'
