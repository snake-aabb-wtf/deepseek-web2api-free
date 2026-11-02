import { Copy } from 'lucide-react'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { StateBadge } from './StateBadge'
import { ReloginButton } from './ReloginButton'
import { toast } from '@/hooks/use-toast'
import { formatUptime, truncateMiddle } from '@/lib/utils'
import type { Account } from '@/lib/types'
import { t } from '@/lib/i18n'

/** Format a unix-seconds timestamp as "YYYY-MM-DD HH:mm:ss" in local time. */
function fmtTs(t: number): string {
  if (!t) return '—'
  const d = new Date(t * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

interface Props {
  account: Account | null
  onClose: () => void
  onRelogin?: () => void
}

export function AccountDetailDrawer({ account, onClose, onRelogin }: Props) {
  const open = !!account

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto">
        {account && (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                {account.email || account.id}
              </SheetTitle>
              <SheetDescription>
                <span className="flex items-center gap-2">
                  <StateBadge state={account.state} />
                  <span className="text-xs text-muted-foreground">·</span>
                  <span className="text-xs">{t('持久化')}</span>
                </span>
              </SheetDescription>
            </SheetHeader>

            <div className="mt-6 space-y-5">
              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('身份')}</h3>
                <DetailRow label="ID" value={account.id} mono copyable />
                <DetailRow label={t('标识')} value={account.email || '—'} />
                <DetailRow label={t('来源')} value="data/accounts.json" />
                <DetailRow label={t('状态')} value={account.state} />
              </section>

              <Separator />

              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('凭据')}</h3>
                <DetailRow label={t('Token 预览')} value={account.token_preview || '—'} mono copyable />
                <DetailRow
                  label={t('Cookies 预览')}
                  value={account.cookies_preview || '—'}
                />
                <DetailRow
                  label={t('凭据指纹')}
                  value={account.credential_fingerprint || '—'}
                  mono
                  copyable
                />
              </section>

              <Separator />

              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('运行时')}</h3>
                <DetailRow label={t('错误次数')} value={String(account.error_count)} />
                <DetailRow
                  label={t('最后使用')}
                  value={
                    account.last_used > 0
                      ? `${fmtTs(account.last_used)} (${t('{d}前', { d: formatUptime(Math.floor(Date.now() / 1000 - account.last_used)) })})`
                      : '—'
                  }
                />
                <DetailRow
                  label={t('创建时间')}
                  value={account.created_at > 0 ? fmtTs(account.created_at) : '—'}
                />
                <DetailRow
                  label={t('更新时间')}
                  value={account.updated_at > 0 ? fmtTs(account.updated_at) : '—'}
                />
              </section>

              {account.last_error && (
                <>
                  <Separator />
                  <section>
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t('最后错误')}</h3>
                    <pre className="rounded-md bg-destructive/5 border border-destructive/20 p-3 text-xs text-destructive whitespace-pre-wrap break-words font-mono">
                      {truncateMiddle(account.last_error, 240, 0)}
                    </pre>
                  </section>
                </>
              )}

              <Separator />

              <div className="flex flex-wrap gap-2">
                {account.state === 'error' && (
                  <ReloginButton accountId={account.id} onDone={onRelogin} />
                )}
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}

function DetailRow({
  label,
  value,
  mono = false,
  copyable = false,
}: {
  label: string
  value: string
  mono?: boolean
  copyable?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className={`flex items-center gap-1.5 min-w-0 text-right ${mono ? 'font-mono text-xs' : ''}`}>
        <span className="truncate" title={value}>{value}</span>
        {copyable && (
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 shrink-0"
            onClick={() => {
              navigator.clipboard.writeText(value).then(
                () => toast({ title: t('已复制'), variant: 'success' }),
                () => toast({ title: t('复制失败'), variant: 'destructive' }),
              )
            }}
            aria-label={t('复制')}
          >
            <Copy className="h-3 w-3" />
          </Button>
        )}
      </span>
    </div>
  )
}
