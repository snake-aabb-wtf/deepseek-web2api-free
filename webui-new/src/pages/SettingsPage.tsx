import { PageHeader } from '@/components/layout/PageHeader'
import { ApiKeyManager } from '@/components/settings/ApiKeyManager'
import { EnvPreview } from '@/components/settings/EnvPreview'

export default function SettingsPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="设置"
        description="管理客户端 API Key，并查看当前运行时配置"
      />
      <ApiKeyManager />
      <EnvPreview />
    </div>
  )
}
