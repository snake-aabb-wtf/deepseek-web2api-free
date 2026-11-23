import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Lang = 'en' | 'zh'

interface LangState {
  lang: Lang
  setLang: (l: Lang) => void
}

/** Persists the UI language. Source strings are Chinese; `t()` maps them to English. */
export const useLangStore = create<LangState>()(
  persist(
    (set) => ({
      lang: 'en',
      setLang: (lang) => {
        set({ lang })
        applyLang(lang)
      },
    }),
    { name: 'ds2api-lang' },
  ),
)

export function applyLang(lang: Lang) {
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  document.title = lang === 'zh' ? 'DS2API · 管理面板' : 'DS2API · Admin Panel'
}
