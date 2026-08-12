import '@testing-library/jest-dom'
import { randomUUID } from 'node:crypto'

// jsdom's built-in Crypto implementation doesn't implement randomUUID();
// useChat.js relies on it to mint session ids, so patch it in for tests.
if (typeof globalThis.crypto?.randomUUID !== 'function') {
  globalThis.crypto = { ...(globalThis.crypto ?? {}), randomUUID }
}
