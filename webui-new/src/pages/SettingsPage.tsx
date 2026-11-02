import { PageHeader } from '@/components/layout/PageHeader'
import { ApiKeyManager } from '@/components/settings/ApiKeyManager'
import { EnvPreview } from '@/components/settings/EnvPreview'
import { t } from '@/lib/i18n'

export default function SettingsPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title={t('设置')}
        description={t('管理客户端 API Key，并查看当前运行时配置')}
      />
      <ApiKeyManager />
      <EnvPreview />
    </div>
  )
}
