import { useEffect, useRef } from 'react'
import { AnimatePresence } from 'framer-motion'
import { MessageCircle } from 'lucide-react'
import ChatBubble from '../components/chat/ChatBubble'
import TypingIndicator from '../components/chat/TypingIndicator'
import ChatInput from '../components/chat/ChatInput'
import EmptyState from '../components/ui/EmptyState'
import useChat from '../hooks/useChat'

const SUGGESTIONS = [
  'Summarize the key points of my uploaded document.',
  'What are the main findings mentioned?',
  'List any dates or figures referenced in the document.',
]

export default function Chat() {
  const { messages, isSending, ask, regenerate } = useChat()
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isSending])

  const lastAssistantId = [...messages].reverse().find((m) => m.role === 'assistant')?.id

  return (
    <div className="flex h-[calc(100vh-7.5rem)] flex-col">
      <div className="flex-1 space-y-5 overflow-y-auto px-1 py-4 sm:px-3">
        {messages.length === 0 ? (
          <EmptyState
            icon={MessageCircle}
            title="Ask anything about your documents"
            description="Upload a PDF, then ask questions here. Answers are grounded in the content you've uploaded."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => ask(suggestion)}
                    className="rounded-full border border-border-light bg-white/60 px-3.5 py-1.5 text-xs text-slate-600 transition-colors hover:bg-white dark:border-border dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            }
          />
        ) : (
          <AnimatePresence initial={false}>
            {messages.map((message) => (
              <ChatBubble
                key={message.id}
                message={message}
                isLast={message.id === lastAssistantId}
                onRegenerate={regenerate}
              />
            ))}
          </AnimatePresence>
        )}
        {isSending && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      <div className="sticky bottom-0 pt-2">
        <ChatInput onSend={ask} disabled={isSending} />
        <p className="mt-2 text-center text-[11px] text-slate-400 dark:text-slate-600">
          InsightAI can make mistakes. Verify important information.
        </p>
      </div>
    </div>
  )
}
