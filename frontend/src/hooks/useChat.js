import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChatMessage, deleteChatSession, getSession } from '../services/chatService'
import getErrorMessage from '../utils/errorMessage'

let idCounter = 0
const nextId = () => `msg-${++idCounter}-${Date.now()}`

const SESSION_KEY = 'insightai_session_id'

// Backend only wants role/content pairs (see ChatRequest.history) — strip
// UI-only fields, and drop error/in-progress bubbles since they aren't
// real answers.
function toHistory(messages) {
  return messages
    .filter((message) => !message.isError && !message.isStreaming)
    .map((message) => ({ role: message.role, content: message.content }))
}

// History for a regenerate() should be everything before the user turn
// being replayed, not including that turn itself (it's sent separately
// as the query).
function historyBeforeQuery(messages, query) {
  let cutoff = messages.length
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'user' && messages[index].content === query) {
      cutoff = index
      break
    }
  }
  return toHistory(messages.slice(0, cutoff))
}

function getOrCreateSessionId() {
  let sessionId = localStorage.getItem(SESSION_KEY)
  if (!sessionId) {
    sessionId = crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, sessionId)
  }
  return sessionId
}

export default function useChat(initialSessionId, initialDocumentIds) {
  const [messages, setMessages] = useState([])
  const [isSending, setIsSending] = useState(false)
  const [isLoadingSession, setIsLoadingSession] = useState(Boolean(initialSessionId))
  const lastQueryRef = useRef('')
  const messagesRef = useRef([])
  const sessionIdRef = useRef(null)
  const documentIdsRef = useRef(initialDocumentIds ?? null)

  // Resume a past conversation (opened from the History page) instead of
  // starting/continuing the localStorage-tracked session — additive to
  // the existing flow below, which is unchanged when no id is passed.
  const loadSession = useCallback(async (sessionId) => {
    setIsLoadingSession(true)
    try {
      const data = await getSession(sessionId)
      sessionIdRef.current = sessionId
      localStorage.setItem(SESSION_KEY, sessionId)
      setMessages(
        data.turns.map((turn) => ({
          id: nextId(),
          role: turn.role,
          content: turn.content,
          sources: [],
          trace: [],
        }))
      )
    } catch (error) {
      console.warn('Failed to load session:', error)
    } finally {
      setIsLoadingSession(false)
    }
  }, [])

  // Initialize session_id on mount: resume initialSessionId if given
  // (navigated here from History), otherwise the existing
  // localStorage-tracked session/fresh-session behavior, unchanged.
  useEffect(() => {
    if (initialSessionId) {
      loadSession(initialSessionId)
    } else {
      sessionIdRef.current = getOrCreateSessionId()
    }
    // Only ever run once per mount — Chat.jsx already remounts this
    // hook via location.key on navigation, so initialSessionId/loadSession
    // changing identity across re-renders (without a real navigation)
    // must not re-trigger a reload mid-conversation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  const updateMessage = useCallback((id, updater) => {
    setMessages((current) => current.map((message) => (message.id === id ? updater(message) : message)))
  }, [])

  const fetchAnswer = useCallback(
    async (query, history, persona) => {
      setIsSending(true)
      const assistantId = nextId()
      setMessages((current) => [
        ...current,
        { id: assistantId, role: 'assistant', content: '', sources: [], trace: [], isStreaming: true },
      ])

      try {
        await streamChatMessage(
          query,
          { history, sessionId: sessionIdRef.current, persona, documentIds: documentIdsRef.current },
          {
            onTrace: (stage, detail) => {
              updateMessage(assistantId, (message) => ({
                ...message,
                // A "reflecting" stage means the pipeline is discarding
                // the current attempt and starting a fresh generation —
                // any text streamed so far belongs to that discarded
                // attempt, so the visible answer resets alongside it
                // (see backend rag_service.py's stream_query docstring).
                content: stage === 'reflecting' ? '' : message.content,
                trace: [...message.trace, { stage, detail }],
              }))
            },
            onChunk: (text) => {
              updateMessage(assistantId, (message) => ({ ...message, content: message.content + text }))
            },
            onDone: (payload) => {
              // Persist session_id returned by server (new or echoed)
              if (payload.session_id) {
                sessionIdRef.current = payload.session_id
                localStorage.setItem(SESSION_KEY, payload.session_id)
              }
              updateMessage(assistantId, (message) => ({
                ...message,
                content: payload.answer,
                sources: payload.sources ?? [],
                retrievalConfidence: payload.retrieval_confidence,
                isClarifyingQuestion: payload.is_clarifying_question ?? false,
                followUpQuestions: payload.follow_up_questions ?? [],
                isStreaming: false,
              }))
            },
            onError: (detail) => {
              updateMessage(assistantId, (message) => ({
                ...message,
                content: getErrorMessage(
                  { response: { data: { detail: detail?.message } } },
                  "I couldn't answer that — please try again."
                ),
                isError: true,
                isStreaming: false,
              }))
            },
          }
        )
      } catch (error) {
        updateMessage(assistantId, (message) => ({
          ...message,
          content: getErrorMessage(error, "I couldn't answer that — please try again."),
          isError: true,
          isStreaming: false,
        }))
      } finally {
        setIsSending(false)
      }
    },
    [updateMessage]
  )

  const ask = useCallback(
    (query, persona) => {
      lastQueryRef.current = query
      const history = toHistory(messagesRef.current)
      setMessages((current) => [...current, { id: nextId(), role: 'user', content: query }])
      fetchAnswer(query, history, persona)
    },
    [fetchAnswer]
  )

  const regenerate = useCallback(() => {
    if (!lastQueryRef.current || isSending) return
    const history = historyBeforeQuery(messagesRef.current, lastQueryRef.current)
    setMessages((current) => {
      const lastIndex = current.length - 1
      if (lastIndex >= 0 && current[lastIndex].role === 'assistant') {
        return current.slice(0, lastIndex)
      }
      return current
    })
    fetchAnswer(lastQueryRef.current, history)
  }, [fetchAnswer, isSending])

  // Clear session (start fresh conversation)
  const clearSession = useCallback(async () => {
    const oldSessionId = sessionIdRef.current
    if (oldSessionId) {
      try {
        await deleteChatSession(oldSessionId)
      } catch (err) {
        // Log but don't block UI — server-side cleanup is best-effort
        console.warn('Failed to delete server-side session:', err)
      }
    }
    localStorage.removeItem(SESSION_KEY)
    sessionIdRef.current = getOrCreateSessionId()
    setMessages([])
  }, [])

  return { messages, isSending, isLoadingSession, ask, regenerate, clearSession, loadSession }
}
