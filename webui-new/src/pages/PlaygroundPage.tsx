import { useState, useRef, useEffect } from 'react'
import { Send, Square, Trash2, FlaskConical, Info } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/stores/auth'
import { ApiCallError } from '@/lib/api'
import { ModelSelector } from '@/components/playground/ModelSelector'
import { MessageList, type ChatMessage, type StreamingState } from '@/components/playground/MessageList'

/** Messages sent to the backend (OpenAI-compatible subset we support). */
interface ApiMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

/** Display labels for the model dropdown — mark the quick/expert modes. */
const MODEL_LABELS: Record<string, string> = {
  'deepseek-chat': 'deepseek-chat（快速 / 默认）',
  'deepseek-reasoner': 'deepseek-reasoner（专家）',
}

export default function PlaygroundPage() {
  const token = useAuthStore((s) => s.token)
  const { toast } = useToast()

  // Request parameters — these map to the fields the backend actually
  // forwards to DeepSeek (see server.py / adapter.py):
  //   model          -> MODEL_ROUTES may map it to model_type (default/expert)
  //   thinking_mode  -> DeepSeek thinking_enabled
  //   search_enabled -> DeepSeek search_enabled
  // temperature / top_p / max_tokens are ignored by the backend, so they
  // are intentionally not offered here.
  const [model, setModel] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [thinking, setThinking] = useState(false)
  const [search, setSearch] = useState(false)

  const [input, setInput] = useState('')
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState<StreamingState | null>(null)
  const [busy, setBusy] = useState(false)
  const [clearOpen, setClearOpen] = useState(false)
  const acRef = useRef<AbortController | null>(null)
  // Tracks the latest accumulated stream so stop/abort handlers read the
  // current value instead of a stale render closure.
  const accRef = useRef<StreamingState>({ reasoning: '', content: '' })

  useEffect(() => () => acRef.current?.abort(), [])

  const handleSend = async () => {
    if (!input.trim() || !model || busy) return
    const userMsg: ChatMessage = { role: 'user', content: input }
    const nextHistory = [...history, userMsg]
    setHistory(nextHistory)
    setInput('')
    setBusy(true)
    setStreaming({ reasoning: '', content: '' })

    const apiMessages: ApiMessage[] = []
    if (systemPrompt.trim()) {
      apiMessages.push({ role: 'system', content: systemPrompt })
    }
    for (const m of nextHistory) apiMessages.push({ role: m.role, content: m.content })

    const ac = new AbortController()
    acRef.current = ac
    const acc: StreamingState = { reasoning: '', content: '' }
    accRef.current = acc

    try {
      const res = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          model,
          messages: apiMessages,
          stream: true,
          thinking_mode: thinking,
          search_enabled: search,
        }),
        signal: ac.signal,
      })

      if (!res.ok || !res.body) {
        const body = await res.text()
        throw new ApiCallError(res.status, `HTTP ${res.status}: ${body.slice(0, 300)}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      // Consume one "data: <json>" payload and accumulate its text.
      const handleEvent = (payload: string) => {
        if (payload === '[DONE]') return
        try {
          const obj = JSON.parse(payload)
          const choice = obj.choices?.[0]
          if (!choice) return
          const delta = choice.delta ?? {}
          if (typeof delta.reasoning_content === 'string') {
            acc.reasoning += delta.reasoning_content
          } else if (typeof delta.content === 'string') {
            acc.content += delta.content
          }
          accRef.current = { reasoning: acc.reasoning, content: acc.content }
          setStreaming({ reasoning: acc.reasoning, content: acc.content })
        } catch {
          // ignore malformed chunk
        }
      }

      // Parse SSE: events separated by a blank line, each "data: <json>"
      // line; "data: [DONE]" terminates. CRLF is normalised so the split
      // works no matter which line ending the transport uses.
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

        let sep
        while ((sep = buf.indexOf('\n\n')) !== -1) {
          const event = buf.slice(0, sep)
          buf = buf.slice(sep + 2)
          for (const line of event.split('\n')) {
            const trimmed = line.trim()
            if (!trimmed.startsWith('data:')) continue
            handleEvent(trimmed.slice(5).trim())
          }
        }
      }

      // Flush a trailing event that reached EOF without a closing blank line.
      if (buf.trim()) {
        for (const line of buf.split('\n')) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data:')) continue
          handleEvent(trimmed.slice(5).trim())
        }
      }

      setHistory([
        ...nextHistory,
        { role: 'assistant', content: acc.content, reasoning: acc.reasoning },
      ])
      setStreaming(null)
    } catch (e) {
      if (ac.signal.aborted) {
        const cur = accRef.current
        if (cur.content.trim() || cur.reasoning.trim()) {
          setHistory([
            ...nextHistory,
            { role: 'assistant', content: cur.content, reasoning: cur.reasoning },
          ])
        } else {
          setHistory(nextHistory)
        }
      } else {
        const msg = e instanceof ApiCallError ? e.message : String(e)
        toast({ title: '请求失败', description: msg, variant: 'destructive' })
      }
      setStreaming(null)
    } finally {
      setBusy(false)
      acRef.current = null
    }
  }

  const handleStop = () => {
    acRef.current?.abort()
  }

  const handleClear = () => {
    setHistory([])
    setStreaming(null)
    setClearOpen(false)
  }

  return (
    <div className="space-y-4 animate-fade-in h-full flex flex-col">
      <PageHeader
        title="Playground"
        description="在线测试 /v1/chat/completions"
        actions={
          <Button
            variant="outline"
            onClick={() => setClearOpen(true)}
            disabled={history.length === 0 || busy}
          >
            <Trash2 className="h-4 w-4" />
            清空
          </Button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[280px,1fr] flex-1 min-h-0">
        {/* Left column: request parameters */}
        <Card className="overflow-y-auto scrollbar-thin">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <FlaskConical className="h-4 w-4" />
              参数
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label>模型</Label>
              <ModelSelector value={model} onChange={setModel} labels={MODEL_LABELS} />
              <p className="text-[11px] text-muted-foreground">
                经 <code className="font-mono">MODEL_ROUTES</code> 映射 DeepSeek
                <code className="font-mono"> model_type</code>（default / expert）
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="system">System 提示</Label>
              <textarea
                id="system"
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                placeholder="可选，例如 'You are a helpful assistant.'"
                className="flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                rows={3}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="thinking">思考模式</Label>
                <p className="text-[11px] text-muted-foreground">
                  对应 DeepSeek <code className="font-mono">thinking_enabled</code>
                </p>
              </div>
              <Switch id="thinking" checked={thinking} onCheckedChange={setThinking} />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="search">联网搜索</Label>
                <p className="text-[11px] text-muted-foreground">
                  对应 DeepSeek <code className="font-mono">search_enabled</code>
                </p>
              </div>
              <Switch id="search" checked={search} onCheckedChange={setSearch} />
            </div>

            <div className="rounded-md border border-dashed p-3 text-[11px] leading-relaxed text-muted-foreground space-y-1">
              <p className="flex items-center gap-1 font-medium text-foreground/80">
                <Info className="h-3.5 w-3.5" />
                参数生效规则
              </p>
              <p>· 服务端 .env 的 MODE / THINKING / SEARCH 优先级高于此处设置</p>
              <p>· MODE=expert 时始终走专家模式（model_type=expert）</p>
              <p>· THINKING/SEARCH 为 enabled/disabled 时强制开关</p>
              <p>· temperature / top_p / max_tokens 后端暂不生效，未提供</p>
            </div>
          </CardContent>
        </Card>

        {/* Right column: conversation */}
        <Card className="flex flex-col min-h-0">
          <CardContent className="flex-1 min-h-0 overflow-y-auto scrollbar-thin p-4">
            <MessageList messages={history} streaming={streaming} />
          </CardContent>
          <div className="border-t p-3 flex items-end gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder="输入消息，回车发送，Shift+回车换行…"
              disabled={busy || !model}
              className="flex-1"
            />
            {busy ? (
              <Button variant="destructive" onClick={handleStop} aria-label="停止">
                <Square className="h-4 w-4" />
              </Button>
            ) : (
              <Button onClick={handleSend} disabled={!input.trim() || !model}>
                <Send className="h-4 w-4" />
                发送
              </Button>
            )}
          </div>
          <div className="border-t px-3 py-1.5 text-[11px] text-muted-foreground">
            Enter 发送 · Shift+Enter 换行 · 模型与参数见左侧
          </div>
        </Card>
      </div>

      {/* Clear-confirm dialog */}
      <AlertDialog open={clearOpen} onOpenChange={setClearOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>清空所有对话？</AlertDialogTitle>
            <AlertDialogDescription>此操作将删除当前会话中的所有消息，不可恢复。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleClear} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              确认清空
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
