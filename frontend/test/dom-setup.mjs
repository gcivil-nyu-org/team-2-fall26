// Minimal jsdom bootstrap for component tests. Imported for its side effect
// at the top of any test file that renders React components — the plain
// function-level tests (friends.test.js, api.test.js, studyCalendar.test.js)
// don't need this and don't import it.
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' })

function define(name, value) {
  Object.defineProperty(globalThis, name, { value, configurable: true, writable: true })
}

for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (key in globalThis && !['navigator', 'window', 'document'].includes(key)) continue
  try {
    define(key, dom.window[key])
  } catch {
    // A handful of jsdom's window properties can't be redefined; skip those.
  }
}

define('window', dom.window)
define('document', dom.window.document)
define('navigator', dom.window.navigator)
