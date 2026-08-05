import { useCallback, useEffect, useRef, useState } from 'react'
import { sendChatMessage } from '../services/chatService'
import getErrorMessage from '../utils/errorMessage'

let idCounter = 0
const nextId = () => `msg-${++idCounter}-${Date.now()}`

// Backend only wants role/content pairs (see ChatRequest.history) — strip
// UI-only fields, and drop error bubbles since they aren't real answers.
function toHistory(messages) {
  return messages
    .filter((message) => !message.isError)
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

  const fetchAnswer = useCallback(async (query, history) => {
    setIsSending(true)
    try {
      const response = await sendChatMessage(query, { history })
      setMessages((current) => [
        ...current,
        {
          id: nextId(),
          role: 'assistant',
          content: response.answer,
          sources: response.sources ?? [],
          retrievedChunks: response.retrieved_chunks ?? [],
        },
      ])
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: nextId(),
          role: 'assistant',
          content: getErrorMessage(error, "I couldn't answer that — please try again."),
          isError: true,
        },
      ])
    } finally {
      setIsSending(false)
    }
  }, [])

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
