import { NavLink, useLocation } from 'react-router-dom'
import { Activity, Users, FlaskConical, Settings, ChevronsLeft, ChevronsRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useState } from 'react'
import { t } from '@/lib/i18n'

interface NavItem {
  to: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  end?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: '概览', icon: Activity, end: true },
  { to: '/accounts', label: '账号池', icon: Users },
  { to: '/playground', label: 'Playground', icon: FlaskConical },
  { to: '/settings', label: '设置', icon: Settings },
]

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()

  return (
    <aside
      className={cn(
        'flex flex-col border-r bg-card transition-[width] duration-200',
        collapsed ? 'w-16' : 'w-56',
      )}
    >
      {/* Brand */}
      <div className="flex h-14 items-center border-b px-4">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-primary to-primary/60 text-primary-foreground font-bold text-sm">
          D
        </div>
        {!collapsed && (
          <div className="ml-2.5 flex-1 overflow-hidden">
            <div className="truncate text-sm font-semibold">DS2API</div>
            <div className="truncate text-[10px] text-muted-foreground tracking-wider">
              {t('管理面板')}
            </div>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 p-2">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon
          const active = item.end
            ? location.pathname === item.to
            : location.pathname.startsWith(item.to)
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={cn(
                'flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm font-medium transition-colors',
                active
                  ? 'bg-primary/15 text-primary'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
              )}
              title={collapsed ? t(item.label) : undefined}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span className="truncate">{t(item.label)}</span>}
            </NavLink>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="border-t p-2">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-center"
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? t('展开侧边栏') : t('折叠侧边栏')}
        >
          {collapsed ? (
            <ChevronsRight className="h-4 w-4" />
          ) : (
            <>
              <ChevronsLeft className="h-4 w-4" />
              <span>{t('折叠')}</span>
            </>
          )}
        </Button>
      </div>
    </aside>
  )
}
