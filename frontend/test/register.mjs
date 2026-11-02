// Registers the JSX loader for `node --test`. Imported via `node --import`
// so it's active before any test file (and anything it imports) loads.
import { register } from 'node:module'

register('./jsx-loader.mjs', import.meta.url)
