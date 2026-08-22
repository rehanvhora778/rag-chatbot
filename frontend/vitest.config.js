import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    // Only our own tests. Without this, vitest walks node_modules and tries to
    // run every package's fixtures.
    include: ['src/**/*.test.{js,jsx}'],
  },
})
