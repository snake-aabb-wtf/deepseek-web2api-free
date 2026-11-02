import { useState } from 'react'
import { RotateCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { post, ApiCallError } from '@/lib/api'
import { toast } from '@/hooks/use-toast'
import type { ReloginResponse } from '@/lib/types'
import { t } from '@/lib/i18n'

interface Props {
  accountId: string
  onDone?: () => void
}

export function ReloginButton({ accountId, onDone }: Props) {
  const [busy, setBusy] = useState(false)
  const handleClick = async () => {
    setBusy(true)
    try {
      const res = await post<ReloginResponse>(`/admin/api/accounts/${encodeURIComponent(accountId)}/relogin`)
      if (res.ok) {
        toast({ title: t('重登录成功'), variant: 'success' })
      } else {
        toast({ title: t('重登录失败'), description: res.message, variant: 'destructive' })
      }
      onDone?.()
    } catch (e) {
      const msg = e instanceof ApiCallError ? e.message : String(e)
      toast({ title: t('重登录失败'), description: msg, variant: 'destructive' })
    } finally {
      setBusy(false)
    }
  }
  return (
    <Button variant="outline" size="sm" onClick={handleClick} disabled={busy}>
      <RotateCw className={`h-3.5 w-3.5 ${busy ? 'animate-spin' : ''}`} />
      {t('重登')}
    </Button>
  )
}
