import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { deleteChatSession, getSession, streamChatMessage } from '../services/chatService'
import useChat from './useChat'

vi.mock('../services/chatService', () => ({
  streamChatMessage: vi.fn(),
  deleteChatSession: vi.fn(),
  getSession: vi.fn(),
}))

const SESSION_KEY = 'insightai_session_id'

describe('useChat', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('mints and persists a session id on first mount when none exists', () => {
    renderHook(() => useChat())
    const stored = localStorage.getItem(SESSION_KEY)
    expect(stored).toBeTruthy()
    expect(stored).toMatch(/^[0-9a-f-]{36}$/)
  })

  it('reuses an existing localStorage session id instead of minting a new one', () => {
    localStorage.setItem(SESSION_KEY, 'existing-session-id')
    renderHook(() => useChat())
    expect(localStorage.getItem(SESSION_KEY)).toBe('existing-session-id')
  })

  it('ask() appends the user message immediately, then fills in the streamed assistant answer', async () => {
    streamChatMessage.mockImplementation(async (query, options, { onChunk, onDone }) => {
      onChunk('Hel')
      onChunk('lo')
      onDone({ answer: 'Hello', sources: [], session_id: 'server-session-id' })
    })

    const { result } = renderHook(() => useChat())

    act(() => {
      result.current.ask('hi there')
    })

    // The user bubble renders synchronously; the assistant bubble starts
    // as an empty streaming placeholder before streamChatMessage resolves.
    expect(result.current.messages).toHaveLength(2)
    expect(result.current.messages[0]).toMatchObject({ role: 'user', content: 'hi there' })

    await waitFor(() => expect(result.current.messages[1]).toMatchObject({ role: 'assistant', content: 'Hello', isStreaming: false }))

    expect(result.current.isSending).toBe(false)
    // The server-echoed session_id replaces the client-minted one, and is
    // what future requests/localStorage should carry.
    expect(localStorage.getItem(SESSION_KEY)).toBe('server-session-id')
  })

  it('ask() marks the assistant bubble as an error when streamChatMessage rejects', async () => {
    streamChatMessage.mockRejectedValue({ message: 'Network Error' })

    const { result } = renderHook(() => useChat())
    act(() => {
      result.current.ask('will fail')
    })

    await waitFor(() => expect(result.current.messages[1]).toMatchObject({ isError: true, isStreaming: false }))
    expect(result.current.messages[1].content).toBe('Unable to reach the server. Please check your connection.')
  })

  it('clearSession() deletes the server-side session and starts a fresh local one', async () => {
    deleteChatSession.mockResolvedValue({ status: 'ok' })
    localStorage.setItem(SESSION_KEY, 'old-session-id')

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.clearSession()
    })

    expect(deleteChatSession).toHaveBeenCalledWith('old-session-id')
    expect(result.current.messages).toEqual([])
    expect(localStorage.getItem(SESSION_KEY)).not.toBe('old-session-id')
  })

  it('loadSession() replaces messages with the resumed conversation turns', async () => {
    getSession.mockResolvedValue({
      session_id: 'resumed-id',
      turns: [
        { role: 'user', content: 'earlier question' },
        { role: 'assistant', content: 'earlier answer' },
      ],
    })

    const { result } = renderHook(() => useChat('resumed-id'))

    await waitFor(() => expect(result.current.isLoadingSession).toBe(false))
    expect(result.current.messages).toHaveLength(2)
    expect(result.current.messages[0]).toMatchObject({ role: 'user', content: 'earlier question' })
    expect(result.current.messages[1]).toMatchObject({ role: 'assistant', content: 'earlier answer' })
    expect(localStorage.getItem(SESSION_KEY)).toBe('resumed-id')
  })
})
