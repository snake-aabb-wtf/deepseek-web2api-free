import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { get } from '@/lib/api'
import { useToast } from '@/hooks/use-toast'

interface EnvInfo {
  name: string
  value: string
  is_default: boolean
  source?: string
  description?: string
}

interface EnvInfoResponse {
  host: string
  port: number
  insecure_public_defaults: boolean
  admin_password_set: boolean
  admin_password_weak: boolean
  accounts_total: number
  crypto: {
    enabled: boolean
    fernet_configured: boolean
  }
  cors: {
    origins: string[]
    allow_credentials: boolean
  }
  trusted_proxies: string[]
  model_routes_configured: boolean
  rate_limit: {
    enabled: boolean
    per_key: number
    per_ip: number
  }
  session_cache_ttl: number
  log_level: string
  log_format: string
  dsml_max_buffer_bytes: number
  uptime_secs: number
  server_version: string
  env_overrides: EnvInfo[]
}

export function EnvPreview() {
  const [info, setInfo] = useState<EnvInfoResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { toast } = useToast()

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    get<EnvInfoResponse>('/admin/api/env')
      .then((d) => !cancelled && setInfo(d))
      .catch((e) => {
        if (cancelled) return
        setError(String(e?.message ?? e))
        toast({ title: '加载环境信息失败', description: String(e?.message ?? e), variant: 'destructive' })
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [toast])

  if (loading && !info) {
    return <div className="text-sm text-muted-foreground">加载中…</div>
  }
  if (error || !info) {
    return <div className="text-sm text-destructive">{error ?? '加载失败'}</div>
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">运行时</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 text-sm">
          <Row k="服务版本" v={info.server_version} />
          <Row k="监听地址" v={`${info.host}:${info.port}`} />
          <Row k="运行时长" v={info.uptime_secs > 0 ? `${Math.floor(info.uptime_secs / 60)} 分钟` : '—'} />
          <Row k="日志" v={`${info.log_level} / ${info.log_format}`} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">安全</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 text-sm">
          <Row
            k="管理员密码"
            v={info.admin_password_weak ? '⚠ 弱密码（默认值）' : '已设置强密码'}
            warn={info.admin_password_weak}
          />
          <Row
            k="ALLOW_INSECURE_PUBLIC_DEFAULTS"
            v={info.insecure_public_defaults ? '已显式允许' : 'false（安全）'}
            warn={info.insecure_public_defaults}
          />
          <Row
            k="凭据加密"
            v={info.crypto.enabled ? `Fernet (${info.crypto.fernet_configured ? 'key 已配置' : 'key 缺失'})` : '明文'}
            warn={!info.crypto.enabled}
          />
          <Row
            k="CORS 允许来源"
            v={info.cors.origins.length === 0 ? '同源（默认）' : info.cors.origins.join(', ')}
          />
          <Row
            k="凭据 cookies"
            v={info.cors.allow_credentials ? '是' : '否'}
          />
          <Row
            k="TRUSTED_PROXIES"
            v={info.trusted_proxies.length === 0 ? '未配置（XFF 不被信任）' : info.trusted_proxies.join(', ')}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">账号池</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 text-sm">
          <Row k="总计" v={String(info.accounts_total)} />
          <Row k="配置方式" v="WebUI / data/accounts.json" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">行为</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1.5 text-sm">
          <Row k="MODEL_ROUTES" v={info.model_routes_configured ? '已配置' : '未配置（仅使用 MODE/THINKING/SEARCH）'} />
          <Row k="限流" v={info.rate_limit.enabled ? `启用 (per-key=${info.rate_limit.per_key}, per-ip=${info.rate_limit.per_ip})` : '关闭'} />
          <Row k="SESSION_CACHE_TTL" v={info.session_cache_ttl === 0 ? '禁用' : `${info.session_cache_ttl} 秒`} />
          <Row k="DSML_MAX_BUFFER_BYTES" v={info.dsml_max_buffer_bytes.toLocaleString('en-US')} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">所有环境变量</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[280px]">名称</TableHead>
                <TableHead>值</TableHead>
                <TableHead className="w-[100px] text-right">来源</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {info.env_overrides.map((e) => (
                <TableRow key={e.name}>
                  <TableCell className="font-mono text-xs">{e.name}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground break-all">
                    {e.value || <span className="italic">空</span>}
                  </TableCell>
                  <TableCell className="text-right">
                    {e.is_default ? (
                      <Badge variant="outline">default</Badge>
                    ) : (
                      <Badge variant="secondary">set</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}

function Row({ k, v, warn }: { k: string; v: string; warn?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted-foreground">{k}</span>
      <span className={warn ? 'text-warning font-medium' : 'text-right'}>{v}</span>
    </div>
  )
}
