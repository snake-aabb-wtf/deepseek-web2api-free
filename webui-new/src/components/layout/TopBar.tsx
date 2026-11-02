import { Moon, Sun, Monitor, LogOut, RefreshCw, Languages } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore, applyTheme } from '@/stores/theme'
import { useLangStore } from '@/stores/lang'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useTheme } from '@/hooks/useTheme'
import { t } from '@/lib/i18n'

interface TopBarProps {
  onRefresh?: () => void
  refreshing?: boolean
}

export function TopBar({ onRefresh, refreshing }: TopBarProps) {
  const theme = useThemeStore((s) => s.theme)
  const setTheme = useThemeStore((s) => s.setTheme)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const { effective } = useTheme()
  const lang = useLangStore((s) => s.lang)
  const setLang = useLangStore((s) => s.setLang)

  const handleLogout = async () => {
    try {
      await fetch('/admin/api/logout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${useAuthStore.getState().token}` },
      })
    } catch {
      // ignore — local logout still works
    }
    logout()
    navigate('/login', { replace: true })
  }

  const ThemeIcon = effective === 'dark' ? Moon : Sun

  return (
    <header className="flex h-14 items-center justify-end gap-2 border-b bg-card/40 px-4 backdrop-blur">
      {onRefresh && (
        <Button variant="ghost" size="icon" onClick={onRefresh} disabled={refreshing} aria-label={t('刷新')}>
          <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
        </Button>
      )}

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={t('语言')}>
            <Languages className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-40">
          <DropdownMenuLabel>{t('语言')}</DropdownMenuLabel>
          <DropdownMenuItem onClick={() => setLang('en')}>
            English
            {lang === 'en' && <span className="ml-auto text-primary">✓</span>}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setLang('zh')}>
            中文
            {lang === 'zh' && <span className="ml-auto text-primary">✓</span>}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={t('切换主题')}>
            <ThemeIcon className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-40">
          <DropdownMenuLabel>{t('主题')}</DropdownMenuLabel>
          <DropdownMenuItem onClick={() => { setTheme('light'); applyTheme('light') }}>
            <Sun className="mr-2 h-4 w-4" /> {t('浅色')}
            {theme === 'light' && <span className="ml-auto text-primary">✓</span>}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => { setTheme('dark'); applyTheme('dark') }}>
            <Moon className="mr-2 h-4 w-4" /> {t('深色')}
            {theme === 'dark' && <span className="ml-auto text-primary">✓</span>}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => { setTheme('system'); applyTheme('system') }}>
            <Monitor className="mr-2 h-4 w-4" /> {t('跟随系统')}
            {theme === 'system' && <span className="ml-auto text-primary">✓</span>}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Button variant="ghost" size="icon" onClick={handleLogout} aria-label={t('退出登录')}>
        <LogOut className="h-4 w-4" />
      </Button>
    </header>
  )
}
