import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/static/frontend/',
  build: {
    outDir: '../static/frontend',
    emptyOutDir: true,
    rollupOptions: {
      input: 'src/main.jsx',
      output: {
        entryFileNames: 'app.js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: ({ names }) => names?.some((name) => name.endsWith('.css')) ? 'app.css' : 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/admin': 'http://127.0.0.1:8000',
    },
  },
})
