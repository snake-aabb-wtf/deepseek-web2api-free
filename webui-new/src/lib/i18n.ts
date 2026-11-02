import { useLangStore } from '@/stores/lang'
import { EN } from './i18n-en'

/**
 * Translate a UI string. Keys are the original Chinese text, so Chinese mode
 * returns the key unchanged and English mode looks it up in `EN`.
 * `{name}` placeholders are filled from `vars`.
 */
export function t(zh: string, vars?: Record<string, string | number>): string {
  let s = useLangStore.getState().lang === 'en' ? (EN[zh] ?? zh) : zh
  if (vars) {
    for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v))
  }
  return s
}
