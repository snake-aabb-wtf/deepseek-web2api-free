import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { LogIn, Eye, EyeOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, ApiCallError } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'
import { toast } from '@/hooks/use-toast'
import { t } from '@/lib/i18n'

export default function LoginPage() {
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const setToken = useAuthStore((s) => s.setToken)
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    if (token) {
      navigate('/', { replace: true })
    }
  }, [token, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!password || loading) return
    setLoading(true)
    setError(null)
    try {
      const res = await api<{ token: string }>('/admin/api/login', {
        method: 'POST',
        body: { password },
      })
      setToken(res.token)
      toast({ title: t('登录成功'), variant: 'success' })
      const from = (location.state as { from?: string })?.from ?? '/'
      navigate(from, { replace: true })
    } catch (e) {
      const msg = e instanceof ApiCallError ? e.message : t('登录失败')
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative flex h-full items-center justify-center overflow-hidden">
      {/* Gradient backdrop */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-br from-primary/10 via-background to-background"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -top-32 left-1/2 -z-10 h-96 w-96 -translate-x-1/2 rounded-full bg-primary/20 blur-3xl dark:bg-primary/10"
      />

      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-xl border bg-card p-8 shadow-lg transition-shadow duration-200 hover:shadow-xl animate-fade-in"
      >
        <div className="mb-6 flex flex-col items-center gap-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary/60 text-primary-foreground text-xl font-bold shadow-md">
            D
          </div>
          <h1 className="text-xl font-semibold tracking-tight">{t('DS2API 管理面板')}</h1>
          <p className="text-sm text-muted-foreground">{t('输入管理密码登录')}</p>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="password">{t('管理密码')}</Label>
            <div className="relative">
              <Input
                id="password"
                type={show ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoFocus
                autoComplete="current-password"
                disabled={loading}
                className="pr-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setShow(!show)}
                className="absolute right-0 top-0 h-9 w-9 text-muted-foreground hover:text-foreground"
                aria-label={show ? t('隐藏密码') : t('显示密码')}
                tabIndex={-1}
              >
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
          </div>

          {error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" disabled={loading || !password}>
            <LogIn className="h-4 w-4" />
            {loading ? t('登录中…') : t('登录')}
          </Button>
        </div>
      </form>
    </div>
  )
}
