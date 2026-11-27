import { useState } from 'react'
import { List, CheckCircle2, XCircle, Ban, Clock, Coins, Globe2 } from 'lucide-react'
import { useApi } from '@/hooks/useApi'
import { PageHeader } from '@/components/layout/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { formatLatency, formatNumber } from '@/lib/utils'
import type { RequestLogResponse, RequestRecord } from '@/lib/types'
import { t, useLanguage } from '@/lib/i18n'

/** Format a unix-seconds timestamp as "yyyy-mm-dd hh:mm:ss" (local time). */
function fmtTs(t: number): string {
  if (!t) return '—'
  const d = new Date(t * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function outcomeIcon(o: string) {
  if (o === 'completed') return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
  if (o === 'cancelled') return <Ban className="h-3.5 w-3.5 text-amber-500" />
  return <XCircle className="h-3.5 w-3.5 text-destructive" />
}

function outcomeLabel(o: string) {
  if (o === 'completed') return t('成功')
  if (o === 'cancelled') return t('取消')
  return t('失败')
}

export default function RequestsPage() {
  useLanguage()
  const [limit, setLimit] = useState(100)
  const [selected, setSelected] = useState<RequestRecord | null>(null)
  const requests = useApi<RequestLogResponse>(`/admin/api/requests?limit=${limit}`, { pollMs: 10000 })

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={t('请求列表')}
        description={t('每次调用一条 · 点结果查看上下文详情')}
      />

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <List className="h-4 w-4" />
            {t('最近请求')}
            <span className="ml-auto flex items-center gap-1 text-xs font-normal text-muted-foreground">
              {t('显示条数')}
              {[20, 50, 100, 200].map((n) => (
                <Button
                  key={n}
                  variant={limit === n ? 'secondary' : 'ghost'}
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={() => setLimit(n)}
                >
                  {n}
                </Button>
              ))}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {requests.loading && !requests.data ? (
            <Skeleton className="h-64 w-full" />
          ) : requests.error ? (
            <div className="flex h-40 flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
              <XCircle className="h-6 w-6 text-destructive" />
              <div>{t('无法加载')}</div>
              <div className="text-xs">{requests.error.message}</div>
            </div>
          ) : requests.data && requests.data.rows.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="px-2 py-1.5 text-left font-medium whitespace-nowrap">{t('时间')}</th>
                    <th className="px-2 py-1.5 text-left font-medium whitespace-nowrap">{t('类型')}</th>
                    <th className="px-2 py-1.5 text-left font-medium whitespace-nowrap">{t('模型')}</th>
                    <th className="px-2 py-1.5 text-left font-medium whitespace-nowrap">{t('来源 IP')}</th>
                    <th className="px-2 py-1.5 text-left font-medium whitespace-nowrap">{t('处理账号')}</th>
                    <th className="px-2 py-1.5 text-right font-medium whitespace-nowrap">{t('耗时')}</th>
                    <th className="px-2 py-1.5 text-right font-medium whitespace-nowrap">{t('输入/输出')}</th>
                    <th className="px-2 py-1.5 text-left font-medium whitespace-nowrap">{t('结果')}</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.data.rows.map((r, i) => (
                    <tr key={`${r.at}-${i}`} className="border-b last:border-0 hover:bg-muted/50">
                      <td className="px-2 py-1.5 whitespace-nowrap tabular-nums">{fmtTs(r.at)}</td>
                      <td className="px-2 py-1.5 whitespace-nowrap">{r.kind}{r.stream ? ' · stream' : ''}</td>
                      <td className="px-2 py-1.5 whitespace-nowrap">{r.model}</td>
                      <td className="px-2 py-1.5 whitespace-nowrap">{r.ip}</td>
                      <td className="px-2 py-1.5 whitespace-nowrap" title={r.account_id || ''}>{r.account || '—'}</td>
                      <td className="px-2 py-1.5 text-right whitespace-nowrap tabular-nums">{formatLatency(r.elapsed_ms)}</td>
                      <td className="px-2 py-1.5 text-right whitespace-nowrap tabular-nums">{formatNumber(r.prompt_tokens)}/{formatNumber(r.completion_tokens)}</td>
                      <td className="px-2 py-1.5 whitespace-nowrap">
                        <button
                          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-secondary"
                          onClick={() => setSelected(r)}
                          title={t('点击查看上下文详情')}
                        >
                          {outcomeIcon(r.outcome)}
                          <span className="underline decoration-dotted underline-offset-2">{outcomeLabel(r.outcome)}</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex h-20 items-center justify-center text-sm text-muted-foreground">{t('暂无数据')}</div>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selected && outcomeIcon(selected.outcome)}
              {t('请求详情')} · {selected ? fmtTs(selected.at) : ''}
            </DialogTitle>
            <DialogDescription>
              {selected && `${selected.kind} · ${selected.model} · ${selected.account || selected.account_id || '—'} · ${selected.ip} · ${formatLatency(selected.elapsed_ms)}`}
            </DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="space-y-4">
              <DetailBlock title={t('请求消息')}>
                {selected.messages && selected.messages.length > 0
                  ? selected.messages.map((m, i) => (
                      <div key={i} className="mb-2 rounded-md border bg-muted/40 p-2">
                        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{m.role}</div>
                        <pre className="whitespace-pre-wrap break-words font-sans text-xs leading-relaxed">{m.content}</pre>
                      </div>
                    ))
                  : <span className="text-muted-foreground">—</span>}
              </DetailBlock>
              <DetailBlock title={t('回复内容')}>
                {selected.content?.reply
                  ? <pre className="whitespace-pre-wrap break-words font-sans text-xs leading-relaxed">{selected.content.reply}</pre>
                  : <span className="text-muted-foreground">—</span>}
              </DetailBlock>
              {selected.content?.thinking && (
                <DetailBlock title={t('思考过程')}>
                  <pre className="whitespace-pre-wrap break-words font-sans text-xs leading-relaxed text-muted-foreground">{selected.content.thinking}</pre>
                </DetailBlock>
              )}
              {selected.error && (
                <DetailBlock title={t('错误信息')}>
                  <pre className="whitespace-pre-wrap break-words font-sans text-xs leading-relaxed text-destructive">{selected.error}</pre>
                </DetailBlock>
              )}
              <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                <Stat icon={Clock} label={t('耗时')} value={formatLatency(selected.elapsed_ms)} />
                <Stat icon={Coins} label={t('输入')} value={formatNumber(selected.prompt_tokens)} />
                <Stat icon={Coins} label={t('输出')} value={formatNumber(selected.completion_tokens)} />
                <Stat icon={Globe2} label={t('来源 IP')} value={selected.ip} />
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function DetailBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</h3>
      <div className="rounded-md border bg-card p-2 text-xs">{children}</div>
    </section>
  )
}

function Stat({ icon: Icon, label, value }: { icon: typeof Clock; label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/40 p-2">
      <div className="flex items-center gap-1 text-[10px] text-muted-foreground"><Icon className="h-3 w-3" />{label}</div>
      <div className="mt-0.5 font-semibold tabular-nums">{value}</div>
    </div>
  )
}
