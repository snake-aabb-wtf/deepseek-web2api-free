import { useEffect, useState } from 'react'
import { Copy, KeyRound, Plus, Trash2, Pencil, Ban, CheckCircle2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useToast } from '@/hooks/use-toast'
import { del, get, patch, post } from '@/lib/api'
import { t, useLanguage } from '@/lib/i18n'

interface ApiKeyRecord {
  id: string
  name: string
  prefix: string
  enabled?: boolean
  created_at: number
}

interface ApiKeyListResponse {
  keys: ApiKeyRecord[]
}

interface ApiKeyCreateResponse {
  key: string
  api_key: ApiKeyRecord
}

export function ApiKeyManager() {
  useLanguage()
  const [keys, setKeys] = useState<ApiKeyRecord[]>([])
  const [name, setName] = useState('')
  const [newKey, setNewKey] = useState<string | null>(null)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  useEffect(() => {
    let cancelled = false
    get<ApiKeyListResponse>('/admin/api/api-keys')
      .then((result) => { if (!cancelled) setKeys(result.keys) })
      .catch((e) => {
        if (cancelled) return
        const message = String(e?.message ?? e)
        setError(message)
        toast({ title: t('加载 API Key 失败'), description: message, variant: 'destructive' })
      })
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [toast])

  /** clipboard API first, execCommand fallback for insecure HTTP. */
  async function copyText(text: string): Promise<boolean> {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text)
        return true
      }
    } catch { /* fall through */ }
    try {
      const ta = document.createElement('textarea')
      ta.value = text; ta.setAttribute('readonly', '')
      ta.style.position = 'fixed'; ta.style.opacity = '0'
      document.body.appendChild(ta); ta.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(ta)
      return ok
    } catch { return false }
  }

  async function createKey() {
    const trimmedName = name.trim()
    if (!trimmedName) {
      toast({ title: t('请填写 Key 名称'), variant: 'destructive' })
      return
    }
    setCreating(true); setError(null)
    try {
      const result = await post<ApiKeyCreateResponse>('/admin/api/api-keys', { name: trimmedName })
      setKeys((current) => [result.api_key, ...current])
      setNewKey(result.key); setName(''); setConfirmingId(null)
      toast({ title: t('API Key 已生成'), description: t('请立即复制并保存完整 Key。') })
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      toast({ title: t('生成 API Key 失败'), description: message, variant: 'destructive' })
    } finally { setCreating(false) }
  }

  async function copyNewKey() {
    if (!newKey) return
    if (await copyText(newKey)) {
      toast({ title: t('已复制 API Key') })
    } else {
      const input = document.querySelector<HTMLInputElement>('input[aria-label="' + t('新生成的 API Key') + '"]')
      if (input) { input.focus(); input.select() }
      toast({ title: t('无法自动复制'), description: t('请按 Ctrl+C 复制已选中的 Key。') })
    }
  }

  async function copyExistingKey(key: ApiKeyRecord) {
    setBusyId(key.id); setError(null)
    try {
      const result = await get<{ key: string }>(`/admin/api/api-keys/${encodeURIComponent(key.id)}/reveal`)
      if (await copyText(result.key)) {
        toast({ title: t('已复制 API Key'), description: key.name })
      } else {
        toast({ title: t('无法自动复制'), description: t('浏览器不允许自动复制，请检查权限。'), variant: 'destructive' })
      }
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      toast({ title: t('复制失败'), description: message, variant: 'destructive' })
    } finally { setBusyId(null) }
  }

  async function saveEdit(key: ApiKeyRecord) {
    const trimmed = editName.trim()
    if (!trimmed) { toast({ title: t('请填写 Key 名称'), variant: 'destructive' }); return }
    setBusyId(key.id); setError(null)
    try {
      const result = await patch<{ api_key: ApiKeyRecord }>(`/admin/api/api-keys/${encodeURIComponent(key.id)}`, { name: trimmed })
      setKeys((current) => current.map((k) => k.id === key.id ? result.api_key : k))
      setEditingId(null)
      toast({ title: t('已保存') })
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      toast({ title: t('保存失败'), description: message, variant: 'destructive' })
    } finally { setBusyId(null) }
  }

  async function toggleEnabled(key: ApiKeyRecord) {
    setBusyId(key.id); setError(null)
    try {
      const result = await patch<{ api_key: ApiKeyRecord }>(`/admin/api/api-keys/${encodeURIComponent(key.id)}`, { enabled: !key.enabled })
      setKeys((current) => current.map((k) => k.id === key.id ? result.api_key : k))
      toast({ title: key.enabled ? t('API Key 已禁用') : t('API Key 已启用') })
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      toast({ title: t('操作失败'), description: message, variant: 'destructive' })
    } finally { setBusyId(null) }
  }

  async function revokeKey(key: ApiKeyRecord) {
    setBusyId(key.id); setError(null)
    try {
      await del(`/admin/api/api-keys/${encodeURIComponent(key.id)}`)
      setKeys((current) => current.filter((item) => item.id !== key.id))
      setConfirmingId(null)
      toast({ title: t('API Key 已撤销'), description: t('{name} 已无法继续调用 API。', { name: key.name }) })
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      toast({ title: t('撤销 API Key 失败'), description: message, variant: 'destructive' })
    } finally { setBusyId(null) }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2 text-base">
              <KeyRound className="h-4 w-4" />
              {t('客户端 API Key')}
            </CardTitle>
            <CardDescription>
              {t('完整 Key 不明文显示；可复制、改名、禁用或撤销。服务端加密保存，仅授权面板可取明文。')}
            </CardDescription>
          </div>
          <Badge variant="secondary">{t('{n} 个', { n: keys.length })}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input value={name} onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void createKey()}
            placeholder={t('Key 名称，例如：Claude Code')} maxLength={64}
            aria-label={t('API Key 名称')} disabled={creating} />
          <Button onClick={() => void createKey()} disabled={creating || !name.trim()}>
            <Plus className="h-4 w-4" />{creating ? t('生成中…') : t('生成 Key')}
          </Button>
        </div>

        {newKey && (
          <div className="space-y-2 rounded-md border border-primary/30 bg-primary/5 p-3">
            <div className="text-sm font-medium">{t('新 Key 只显示这一次，请现在复制保存。')}</div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input value={newKey} readOnly className="font-mono text-xs select-all" aria-label={t('新生成的 API Key')} />
              <Button variant="outline" onClick={() => void copyNewKey()}><Copy className="h-4 w-4" />{t('复制')}</Button>
              <Button variant="ghost" onClick={() => setNewKey(null)}>{t('完成')}</Button>
            </div>
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        {loading ? (
          <p className="text-sm text-muted-foreground">{t('正在加载 Key…')}</p>
        ) : keys.length === 0 ? (
          <p className="rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">
            {t('还没有客户端 API Key。生成一个后即可用于 OpenAI 兼容接口。')}
          </p>
        ) : (
          <div className="divide-y rounded-md border">
            {keys.map((key) => {
              if (editingId === key.id) {
                return (
                  <div key={key.id} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center">
                    <Input value={editName} onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && void saveEdit(key)}
                      maxLength={64} aria-label={t('Key 新名称')} autoFocus />
                    <div className="flex shrink-0 gap-2">
                      <Button size="sm" onClick={() => void saveEdit(key)} disabled={busyId === key.id}>{t('保存')}</Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>{t('取消')}</Button>
                    </div>
                  </div>
                )
              }
              return (
                <div key={key.id} className={`flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between ${key.enabled === false ? 'opacity-60' : ''}`}>
                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">{key.name}</span>
                      {key.enabled === false && <Badge variant="destructive" className="text-[10px]">{t('已禁用')}</Badge>}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <code className="font-mono">{key.prefix}…</code>
                      <span>{t('创建于 {date}', { date: new Date(key.created_at * 1000).toLocaleString() })}</span>
                    </div>
                  </div>
                  {confirmingId === key.id ? (
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="text-xs text-destructive">{t('确认撤销？')}</span>
                      <Button size="sm" variant="destructive" onClick={() => void revokeKey(key)} disabled={busyId === key.id}>
                        {busyId === key.id ? t('撤销中…') : t('确认')}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirmingId(null)} disabled={busyId === key.id}>{t('取消')}</Button>
                    </div>
                  ) : (
                    <div className="flex shrink-0 items-center gap-1">
                      <Button size="sm" variant="ghost" className="h-8 px-2" onClick={() => void copyExistingKey(key)}
                        disabled={busyId === key.id} title={t('复制完整 Key')} aria-label={t('复制 {name}', { name: key.name })}>
                        <Copy className="h-4 w-4" />
                      </Button>
                      <Button size="sm" variant="ghost" className="h-8 px-2" onClick={() => { setEditingId(key.id); setEditName(key.name) }}
                        disabled={busyId === key.id} title={t('编辑名称')} aria-label={t('编辑 {name}', { name: key.name })}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button size="sm" variant="ghost" className="h-8 px-2" onClick={() => void toggleEnabled(key)}
                        disabled={busyId === key.id} title={key.enabled === false ? t('启用') : t('禁用')}
                        aria-label={t('切换 {name} 启用状态', { name: key.name })}>
                        {key.enabled === false ? <CheckCircle2 className="h-4 w-4" /> : <Ban className="h-4 w-4" />}
                      </Button>
                      <Button size="sm" variant="ghost" className="h-8 px-2 text-muted-foreground hover:text-destructive"
                        onClick={() => setConfirmingId(key.id)} title={t('撤销')} aria-label={t('撤销 {name}', { name: key.name })}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
