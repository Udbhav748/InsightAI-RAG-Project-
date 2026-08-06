import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChatMessage } from '../services/chatService'
import getErrorMessage from '../utils/errorMessage'

let idCounter = 0
const nextId = () => `msg-${++idCounter}-${Date.now()}`

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

export default function useChat() {
  const [messages, setMessages] = useState([])
  const [isSending, setIsSending] = useState(false)
  const lastQueryRef = useRef('')
  const messagesRef = useRef([])

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  const updateMessage = useCallback((id, updater) => {
    setMessages((current) => current.map((message) => (message.id === id ? updater(message) : message)))
  }, [])

  const fetchAnswer = useCallback(
    async (query, history) => {
      setIsSending(true)
      const assistantId = nextId()
      setMessages((current) => [
        ...current,
        { id: assistantId, role: 'assistant', content: '', sources: [], trace: [], isStreaming: true },
      ])

      try {
        await streamChatMessage(
          query,
          { history },
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
              updateMessage(assistantId, (message) => ({
                ...message,
                content: payload.answer,
                sources: payload.sources ?? [],
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
    (query) => {
      lastQueryRef.current = query
      const history = toHistory(messagesRef.current)
      setMessages((current) => [...current, { id: nextId(), role: 'user', content: query }])
      fetchAnswer(query, history)
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

  return { messages, isSending, ask, regenerate }
}
