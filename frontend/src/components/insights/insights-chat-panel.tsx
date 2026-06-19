import { Sparkles, User } from 'lucide-react'
import { marked } from 'marked'
import { useEffect, useRef } from 'react'
import type {
  InsightsChatMessage,
  InsightsChatStatus,
} from '@/hooks/use-insights-chat'
import { cn } from '@/lib/utils'

const SUGGESTED_PROMPTS = [
  'What is the most popular optional install in the last 90 days?',
  'What software has the most failed installs?',
  'Show Chrome install counts grouped by version.',
  'How many Mac Studios have Chrome installed?',
]

type InsightsChatPanelProps = {
  messages: InsightsChatMessage[]
  status: InsightsChatStatus
  error: string | null
  isLoading: boolean
  input: string
  onInputChange: (value: string) => void
  onSubmit: (text: string) => void
  onStop: () => void
}

export function InsightsChatPanel({
  messages,
  status,
  error,
  isLoading,
  input,
  onInputChange,
  onSubmit,
  onStop,
}: InsightsChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, status])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit(input)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
        {messages.length === 0 ? (
          <EmptyState onSelect={onSubmit} />
        ) : (
          <div className="flex flex-col gap-5">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            {status === 'submitted' && <TypingIndicator />}
          </div>
        )}
      </div>

      {error && error !== 'not-configured' && (
        <div className="mx-4 mb-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="border-t border-border px-4 py-4">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSubmit(input)
          }}
          className="relative flex items-end gap-2 rounded-xl border border-border bg-muted transition-colors focus-within:border-primary/50"
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder="Ask about fleet check-ins, versions, or auto-promote…"
            rows={1}
            className="max-h-32 min-h-[44px] flex-1 resize-none overflow-y-auto bg-transparent px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement
              target.style.height = 'auto'
              target.style.height = `${Math.min(target.scrollHeight, 128)}px`
            }}
          />
          {isLoading ? (
            <button
              type="button"
              onClick={onStop}
              className="m-1.5 rounded-lg bg-destructive/15 p-2 text-destructive transition-colors hover:bg-destructive/25"
              aria-label="Stop generating"
            >
              <StopIcon />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="m-1.5 rounded-lg bg-primary p-2 text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-30"
              aria-label="Send message"
            >
              <SendIcon />
            </button>
          )}
        </form>
        <p className="mt-2 text-center text-xs text-muted-foreground">
          Powered by Gemini. Answers use live fleet and Munki data via tool
          calling.
        </p>
      </div>
    </div>
  )
}

function EmptyState({ onSelect }: { onSelect: (text: string) => void }) {
  return (
    <div className="flex h-full min-h-64 flex-col items-center justify-center gap-8 py-8">
      <div className="text-center">
        <Sparkles className="mx-auto mb-4 h-10 w-10 text-primary" aria-hidden />
        <h2 className="mb-2 text-xl font-semibold">Fleet AI Insights</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          Ask natural-language questions about check-ins, installed software
          versions, and auto-promote status across your managed Mac fleet.
        </p>
      </div>
      <div className="grid w-full max-w-xl grid-cols-1 gap-3 sm:grid-cols-2">
        {SUGGESTED_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onSelect(prompt)}
            className="rounded-xl border border-border bg-card px-4 py-3 text-left text-sm text-muted-foreground transition-all hover:border-primary/40 hover:bg-muted hover:text-foreground"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  )
}

function MessageBubble({ message }: { message: InsightsChatMessage }) {
  const isUser = message.role === 'user'

  return (
    <div className={cn('flex gap-3', isUser && 'flex-row-reverse')}>
      <Avatar isUser={isUser} />
      <div
        className={cn(
          'max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed',
          isUser
            ? 'rounded-br-md bg-primary text-primary-foreground'
            : 'rounded-bl-md border border-border bg-card text-card-foreground',
        )}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{message.content}</span>
        ) : (
          <>
            {message.statusMessage && !message.content && (
              <p className="text-muted-foreground italic">
                {message.statusMessage}
              </p>
            )}
            {message.content ? (
              <div
                className="prose-chat"
                dangerouslySetInnerHTML={{
                  __html: marked.parse(message.content, { async: false }),
                }}
              />
            ) : null}
            {message.toolsUsed && message.toolsUsed.length > 0 && (
              <p className="mt-2 border-t border-border/60 pt-2 text-xs text-muted-foreground">
                {message.toolsUsed
                  .map((t) => `${t.name}: ${t.summary}`)
                  .join(' · ')}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Avatar({ isUser }: { isUser: boolean }) {
  return (
    <div
      className={cn(
        'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold',
        isUser
          ? 'bg-primary/15 text-primary'
          : 'bg-muted text-muted-foreground',
      )}
    >
      {isUser ? <User className="h-4 w-4" aria-hidden /> : 'AI'}
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <Avatar isUser={false} />
      <div className="flex items-center gap-1.5 pt-1">
        <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
        <span
          className="h-2 w-2 animate-pulse rounded-full bg-primary"
          style={{ animationDelay: '0.2s' }}
        />
        <span
          className="h-2 w-2 animate-pulse rounded-full bg-primary"
          style={{ animationDelay: '0.4s' }}
        />
      </div>
    </div>
  )
}

function SendIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <title>Send</title>
      <path d="M22 2L11 13" />
      <path d="M22 2L15 22L11 13L2 9L22 2Z" />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <title>Stop</title>
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  )
}
