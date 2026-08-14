import '@testing-library/jest-dom'
import { randomUUID } from 'node:crypto'

// jsdom's built-in Crypto implementation doesn't implement randomUUID();
// useChat.js relies on it to mint session ids, so patch it in for tests.
if (typeof globalThis.crypto?.randomUUID !== 'function') {
  globalThis.crypto = { ...(globalThis.crypto ?? {}), randomUUID }
}

if (typeof globalThis.DOMMatrix === 'undefined') {
  globalThis.DOMMatrix = class DOMMatrix {}
}

if (typeof window !== 'undefined') {
  window.DOMMatrix = globalThis.DOMMatrix
  Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || vi.fn()

  const mockCreateObjectURL = vi.fn(() => 'blob:http://localhost/mock-leaf-preview')
  const mockRevokeObjectURL = vi.fn()
  window.URL.createObjectURL = mockCreateObjectURL
  window.URL.revokeObjectURL = mockRevokeObjectURL
  globalThis.URL.createObjectURL = mockCreateObjectURL
  globalThis.URL.revokeObjectURL = mockRevokeObjectURL
}
