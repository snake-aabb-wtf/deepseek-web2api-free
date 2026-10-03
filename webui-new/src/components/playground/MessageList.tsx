import { useEffect, useRef } from 'react'
import { User, Bot } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

/**
 * A single conversation turn. `reasoning` (DeepSeek expert-mode
 * thinking text) renders in a collapsible block above the content.
 */
export interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
  reasoning?: string
}

/** Live state while a response is streaming in. */
export interface StreamingState {
  reasoning: string
  content: string
}

interface Props {
  messages: ChatMessage[]
  streaming?: StreamingState | null
}

/** Collapsible reasoning block shown above the answer. */
function ReasoningBlock({ text }: { text: string }) {
  if (!text.trim()) return null
  return (
    <details className="mb-2 rounded-md bg-muted/60 p-2 text-xs text-muted-foreground">
      <summary className="cursor-pointer select-none font-medium">推理过程</summary>
      <div className="mt-1.5 max-h-48 overflow-y-auto whitespace-pre-wrap break-words font-mono leading-relaxed">
        {text}
      </div>
    </details>
  )
}

export function MessageList({ messages, streaming }: Props) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, streaming?.content.length, streaming?.reasoning.length])

  if (messages.length === 0 && !streaming) {
    return (
      <Card className="flex h-full items-center justify-center border-dashed">
        <CardContent className="text-center text-sm text-muted-foreground py-12">
          <Bot className="mx-auto h-8 w-8 mb-2 opacity-40 text-primary" />
          <p>在左侧输入消息并点击"发送"</p>
          <p className="mt-1 text-xs">客户端 API Key 可在设置页创建</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      {messages.map((m, i) => (
        <div
          key={i}
          className={cn('flex gap-3', m.role === 'user' ? 'justify-end' : 'justify-start')}
        >
          {m.role !== 'user' && (
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
              <Bot className="h-3.5 w-3.5" />
            </div>
          )}
          <div
            className={cn(
              'max-w-[80%] rounded-lg border px-3 py-2 text-sm shadow-sm',
              m.role === 'user'
                ? 'bg-gradient-to-br from-primary/15 to-primary/5 border-primary/25'
                : 'bg-card',
            )}
          >
            {m.role !== 'user' && m.reasoning && <ReasoningBlock text={m.reasoning} />}
            <div className="whitespace-pre-wrap break-words">
              {m.content || <span className="text-muted-foreground italic">（空）</span>}
            </div>
          </div>
          {m.role === 'user' && (
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-secondary text-secondary-foreground">
              <User className="h-3.5 w-3.5" />
            </div>
          )}
        </div>
      ))}

      {streaming && (
        <div className="flex gap-3 justify-start">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
            <Bot className="h-3.5 w-3.5" />
          </div>
          <div className="max-w-[80%] rounded-lg border bg-card px-3 py-2 text-sm shadow-sm">
            {streaming.reasoning && (
              <div className="mb-2 rounded-md bg-muted/60 p-2 text-xs text-muted-foreground">
                <div className="font-medium">推理过程</div>
                <div className="mt-1 whitespace-pre-wrap break-words font-mono leading-relaxed">
                  {streaming.reasoning}
                </div>
              </div>
            )}
            <div className="whitespace-pre-wrap break-words">
              {streaming.content}
              <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-primary align-middle" />
            </div>
          </div>
        </div>
      )}
      <div ref={endRef} />
    </div>
  )
}
