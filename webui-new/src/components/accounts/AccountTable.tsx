import { Pencil, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { StateBadge } from './StateBadge'
import { ReloginButton } from './ReloginButton'
import { truncateMiddle } from '@/lib/utils'
import type { Account } from '@/lib/types'

interface Props {
  accounts: Account[]
  onEdit: (a: Account) => void
  onDelete: (a: Account) => void
  onSelect: (a: Account) => void
}

export function AccountTable({ accounts, onEdit, onDelete, onSelect }: Props) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>标识</TableHead>
          <TableHead>来源</TableHead>
          <TableHead>状态</TableHead>
          <TableHead>Token</TableHead>
          <TableHead>Cookies</TableHead>
          <TableHead className="text-right">错误</TableHead>
          <TableHead>最后错误</TableHead>
          <TableHead className="text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {accounts.map((a) => (
          <TableRow
              key={a.id}
              className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => onSelect(a)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelect(a)
                }
              }}
              tabIndex={0}
              role="button"
              aria-label={`查看账号 ${a.email || a.id}`}
            >
              <TableCell>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="block max-w-[160px] truncate font-medium">
                      {a.email || a.id.slice(0, 10)}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>{a.id}</TooltipContent>
                </Tooltip>
              </TableCell>
              <TableCell>
                <Badge variant="secondary">持久化</Badge>
              </TableCell>
              <TableCell>
                <StateBadge state={a.state} />
              </TableCell>
              <TableCell>
                <span className="font-mono text-xs text-muted-foreground">
                  {a.token_preview || '—'}
                </span>
              </TableCell>
              <TableCell>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="block max-w-[180px] truncate text-sm text-muted-foreground">
                      {a.cookies_preview || '—'}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>{a.cookies_preview || '—'}</TooltipContent>
                </Tooltip>
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {a.error_count > 0 ? (
                  <span className="text-warning font-semibold">{a.error_count}</span>
                ) : (
                  <span className="text-muted-foreground">0</span>
                )}
              </TableCell>
              <TableCell>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="block max-w-[200px] truncate text-xs text-muted-foreground">
                      {a.last_error || '—'}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    <span className="max-w-md break-words font-mono text-xs">
                      {truncateMiddle(a.last_error || '—', 200, 0)}
                    </span>
                  </TooltipContent>
                </Tooltip>
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                  {a.state === 'error' && <ReloginButton accountId={a.id} />}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => onEdit(a)}
                        aria-label="编辑"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>编辑</TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => onDelete(a)}
                        aria-label="删除"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>删除</TooltipContent>
                  </Tooltip>
                </div>
              </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
