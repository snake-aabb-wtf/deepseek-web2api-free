import React from 'react'
import ReactDOM from 'react-dom/client'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/toaster'
import { App } from './App'
import './styles/globals.css'

// Apply the persisted theme as early as possible so we don't flash a
// light UI for users who prefer dark.
import { useThemeStore, applyTheme } from './stores/theme'
applyTheme(useThemeStore.getState().theme)

import { useLangStore, applyLang } from './stores/lang'
applyLang(useLangStore.getState().lang)

// Strings are translated at render time via t(), so remount the app when the
// language changes to re-render everything, including memoized parts.
function Root() {
  const lang = useLangStore((s) => s.lang)
  return <App key={lang} />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <TooltipProvider delayDuration={200}>
      <Root />
      <Toaster />
    </TooltipProvider>
  </React.StrictMode>,
)
