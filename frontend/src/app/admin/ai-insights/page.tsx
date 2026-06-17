import { useAtom } from 'jotai'
import { Sparkles } from 'lucide-react'
import { useMemo } from 'react'
import { useAuth } from '@/components/auth-provider'
import { InsightsChatPanel } from '@/components/insights/insights-chat-panel'
import { InsightsDataPanel } from '@/components/insights/insights-data-panel'
import { PageHeading } from '@/components/page-heading'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { useDocumentTitle } from '@/hooks/use-document-title'
import { useInsightsChat } from '@/hooks/use-insights-chat'
import {
  insightsChatInputAtom,
  insightsDataPanelOpenAtom,
} from '@/lib/atoms/insights-chat'
import { PAGE_KEYS } from '@/lib/page-keys'
import { cn } from '@/lib/utils'

export default function AdminAiInsightsPage() {
  useDocumentTitle('Admin', 'AI Insights')
  const { canRead, loading } = useAuth()
  const [input, setInput] = useAtom(insightsChatInputAtom)
  const [dataPanelOpen, setDataPanelOpen] = useAtom(insightsDataPanelOpenAtom)

  const {
    messages,
    sendMessage,
    clearConversation,
    status,
    error,
    stop,
    isLoading,
  } = useInsightsChat()

  const latestAssistant = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === 'assistant') return messages[i]
    }
    return null
  }, [messages])

  const tableData = latestAssistant?.tableData ?? null
  const toolsUsed = latestAssistant?.toolsUsed ?? []

  const handleSubmit = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    void sendMessage(trimmed)
    setInput('')
    if (tableData) setDataPanelOpen(true)
  }

  if (!loading && !canRead(PAGE_KEYS.adminAiInsights)) {
    return (
      <p className="text-destructive">You do not have access to this page.</p>
    )
  }

  return (
    <div className="flex min-h-0 flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeading icon={Sparkles} accent="settings" title="AI Insights" />
        {messages.length > 0 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={clearConversation}
          >
            Clear conversation
          </Button>
        )}
      </div>

      {error === 'not-configured' && (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardHeader>
            <CardTitle>AI Insights is not configured</CardTitle>
            <CardDescription>
              Set <code className="text-xs">INSIGHTS_ENABLED=true</code> and{' '}
              <code className="text-xs">GEMINI_API_KEY</code> in the server
              environment, then restart the API.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      <div
        className={cn(
          'flex min-h-128 flex-col overflow-hidden rounded-xl border bg-card lg:h-[calc(100vh-6rem)] lg:flex-row',
        )}
      >
        <div
          className={cn(
            'flex min-h-0 min-w-0 flex-col',
            dataPanelOpen ? 'lg:w-[65%]' : 'flex-1',
          )}
        >
          <InsightsChatPanel
            messages={messages}
            status={status}
            error={error}
            isLoading={isLoading}
            input={input}
            onInputChange={setInput}
            onSubmit={handleSubmit}
            onStop={stop}
          />
        </div>

        <InsightsDataPanel
          tableData={tableData}
          toolsUsed={toolsUsed}
          open={dataPanelOpen}
          onToggle={() => setDataPanelOpen((v) => !v)}
        />
      </div>
    </div>
  )
}
