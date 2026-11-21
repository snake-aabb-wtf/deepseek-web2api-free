import React from 'react'
import ReactDOM from 'react-dom/client'
import { Root } from './Root'
import './styles/globals.css'

// Apply the persisted theme as early as possible so we don't flash a
// light UI for users who prefer dark.
import { useThemeStore, applyTheme } from './stores/theme'
applyTheme(useThemeStore.getState().theme)

import { useLangStore, applyLang } from './stores/lang'
applyLang(useLangStore.getState().lang)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
