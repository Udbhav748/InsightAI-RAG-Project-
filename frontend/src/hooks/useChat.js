import { useCallback, useRef, useState } from 'react'
import { sendChatMessage } from '../services/chatService'
import getErrorMessage from '../utils/errorMessage'

let idCounter = 0
const nextId = () => `msg-${++idCounter}-${Date.now()}`

export default function useChat() {
  const [messages, setMessages] = useState([])
  const [isSending, setIsSending] = useState(false)
  const lastQueryRef = useRef('')

  const fetchAnswer = useCallback(async (query) => {
    setIsSending(true)
    try {
      const response = await sendChatMessage(query)
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
      setMessages((current) => [...current, { id: nextId(), role: 'user', content: query }])
      fetchAnswer(query)
    },
    [fetchAnswer]
  )

  const regenerate = useCallback(() => {
    if (!lastQueryRef.current || isSending) return
    setMessages((current) => {
      const lastIndex = current.length - 1
      if (lastIndex >= 0 && current[lastIndex].role === 'assistant') {
        return current.slice(0, lastIndex)
      }
      return current
    })
    fetchAnswer(lastQueryRef.current)
  }, [fetchAnswer, isSending])

  return { messages, isSending, ask, regenerate }
}
