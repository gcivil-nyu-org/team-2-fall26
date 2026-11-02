// Minimal Node.js ESM loader that transforms .jsx files with esbuild so the
// plain `node --test` runner (no Vite, no Babel, no Jest) can import React
// components directly. Mirrors the JSX runtime Vite already uses for the app
// itself (@vitejs/plugin-react's default "automatic" runtime), so a
// component behaves identically whether it's loaded by the app build or by
// a test.
//
// Also resolves Vite-style extensionless relative imports (e.g.
// `from './api'`, which Vite's own bundler resolver expands to './api.js').
// Node's native ESM resolver requires the extension, so this retries with
// .jsx/.js when the bare specifier doesn't resolve on its own — needed only
// because this is the first thing in the project to load .jsx files outside
// of Vite.
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { transform } from 'esbuild'

function withFormat(resolved) {
  if (resolved.url.endsWith('.jsx')) {
    return { ...resolved, format: 'jsx-module', shortCircuit: true }
  }
  return resolved
}

export async function resolve(specifier, context, nextResolve) {
  try {
    return withFormat(await nextResolve(specifier, context))
  } catch (err) {
    const isRelative = specifier.startsWith('./') || specifier.startsWith('../')
    if (err?.code === 'ERR_MODULE_NOT_FOUND' && isRelative) {
      for (const ext of ['.jsx', '.js']) {
        try {
          return withFormat(await nextResolve(specifier + ext, context))
        } catch {
          // try the next extension
        }
      }
    }
    throw err
  }
}

export async function load(url, context, nextLoad) {
  if (context.format === 'jsx-module' || url.endsWith('.jsx')) {
    const source = await readFile(fileURLToPath(url), 'utf8')
    const { code } = await transform(source, {
      loader: 'jsx',
      format: 'esm',
      jsx: 'automatic',
      sourcefile: url,
    })
    return { format: 'module', source: code, shortCircuit: true }
  }
  return nextLoad(url, context)
}
