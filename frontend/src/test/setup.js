import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// React Testing Library does not unmount between tests on its own when
// globals are enabled, and a leaked component keeps its timers and its
// listeners — which is how one test starts failing because of another.
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

// jsdom implements neither, and framer-motion and the chat scroll both call
// them. Left unstubbed they throw inside a render and the failure points at
// the component rather than at the environment.
globalThis.IntersectionObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = globalThis.IntersectionObserver
Element.prototype.scrollIntoView = vi.fn()
