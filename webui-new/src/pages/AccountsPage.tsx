import { useState } from 'react'
import { Plus, RefreshCw, Users } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import { useApi } from '@/hooks/useApi'
import { del, ApiCallError } from '@/lib/api'
import { toast } from '@/hooks/use-toast'
import { AccountForm } from '@/components/accounts/AccountForm'
import { AccountTable } from '@/components/accounts/AccountTable'
import { AccountDetailDrawer } from '@/components/accounts/AccountDetailDrawer'
import type { Account, AccountsResponse } from '@/lib/types'

export default function AccountsPage() {
  const { data, error, loading, refresh } = useApi<AccountsResponse>('/admin/api/accounts', {
    pollMs: 10000,
  })
  const [addOpen, setAddOpen] = useState(false)
  const [editing, setEditing] = useState<Account | null>(null)
  const [viewing, setViewing] = useState<Account | null>(null)
  const [deleting, setDeleting] = useState<Account | null>(null)

  const accounts = data?.accounts ?? []

  const handleDelete = async () => {
    if (!deleting) return
    try {
      await del(`/admin/api/accounts/${encodeURIComponent(deleting.id)}`)
      toast({ title: '账号已删除', variant: 'success' })
      setDeleting(null)
      refresh()
    } catch (e) {
      const msg = e instanceof ApiCallError ? e.message : String(e)
      toast({ title: '删除失败', description: msg, variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="账号池"
        description={`管理 DeepSeek 账号 · 共 ${data?.total ?? '—'} 个`}
        actions={
          <>
            <Button variant="outline" onClick={refresh} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              刷新
            </Button>
            <Button onClick={() => setAddOpen(true)}>
              <Plus className="h-4 w-4" />
              添加账号
            </Button>
          </>
        }
      />

      <Card>
        <CardContent className="p-0">
          {loading && !data ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : error ? (
            <div className="p-8 text-center text-sm text-destructive">
              加载失败：{error.message}
            </div>
          ) : accounts.length === 0 ? (
            <div className="p-12 text-center">
              <Users className="mx-auto h-10 w-10 text-muted-foreground/40" />
              <h3 className="mt-3 text-sm font-medium">暂无账号</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                点击右上角“添加账号”，也可以将账号写入 data/accounts.json。
              </p>
            </div>
          ) : (
            <AccountTable
              accounts={accounts}
              onEdit={(a) => setEditing(a)}
              onDelete={(a) => setDeleting(a)}
              onSelect={(a) => setViewing(a)}
            />
          )}
        </CardContent>
      </Card>

      {/* Add dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>添加账号</DialogTitle>
            <DialogDescription>输入 DeepSeek 账号的 Token 与 Cookies 即可使用</DialogDescription>
          </DialogHeader>
          <AccountForm
            onSaved={() => {
              setAddOpen(false)
              refresh()
            }}
            onCancel={() => setAddOpen(false)}
          />
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑账号</DialogTitle>
            <DialogDescription>
              留空 Token / Cookies 表示不修改对应字段
            </DialogDescription>
          </DialogHeader>
          {editing && (
            <AccountForm
              account={editing}
              onSaved={() => {
                setEditing(null)
                refresh()
              }}
              onCancel={() => setEditing(null)}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除账号？</AlertDialogTitle>
            <AlertDialogDescription>
              将删除账号 <code className="font-mono text-xs">{deleting?.id}</code>。
              此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Detail drawer */}
      <AccountDetailDrawer
        account={viewing}
        onClose={() => setViewing(null)}
        onRelogin={refresh}
      />
    </div>
  )
}
