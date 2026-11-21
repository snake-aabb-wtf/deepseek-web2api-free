import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

// Regression: switching the UI language must re-render in place, not remount
// the routed app (which wiped the one-time API key and Playground state).

const NEW_KEY = 'sk-test-0123456789abcdefghijklmnop'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mockBackend() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/admin/api/api-keys') && method === 'POST') {
        return json({
          key: NEW_KEY,
          api_key: { id: 'k1', name: 'test client', prefix: 'sk-test', created_at: 1_700_000_000 },
        })
      }
      if (url.endsWith('/admin/api/api-keys')) return json({ keys: [] })
      if (url.endsWith('/v1/models')) {
        return json({ object: 'list', data: [{ id: 'deepseek-chat', object: 'model' }] })
      }
      return json({ detail: 'not mocked' }, 500)
    }),
  )
}

/** Render the real app (router included) at `path`, logged in, in English. */
async function renderApp(path: string) {
  vi.resetModules()
  window.history.pushState({}, '', `/webui${path}`)
  const { useAuthStore } = await import('@/stores/auth')
  const { useLangStore } = await import('@/stores/lang')
  useAuthStore.setState({ token: 'test-token' })
  useLangStore.setState({ lang: 'en' })
  const { Root } = await import('@/Root')
  render(<Root />)
  const setLang = (lang: 'en' | 'zh') => act(() => useLangStore.getState().setLang(lang))
  return { setLang }
}

beforeEach(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
  window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
  try {
    localStorage.clear()
  } catch {
    // storage unavailable — stores fall back to defaults
  }
  mockBackend()
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('language switch keeps page state', () => {
  it('keeps a freshly generated API key visible', async () => {
    const { setLang } = await renderApp('/settings')

    fireEvent.change(await screen.findByLabelText('API key name'), { target: { value: 'test client' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create key' }))
    expect(await screen.findByLabelText('New API key')).toHaveProperty('value', NEW_KEY)

    setLang('zh')

    // Text switched to Chinese, but the one-time key is still shown.
    expect(screen.getByLabelText('新生成的 API Key')).toHaveProperty('value', NEW_KEY)
    expect(screen.getByText('新 Key 只显示这一次，请现在复制保存。')).toBeTruthy()

    setLang('en')
    expect(screen.getByLabelText('New API key')).toHaveProperty('value', NEW_KEY)
  })

  it('keeps Playground draft, system prompt and switches', async () => {
    const { setLang } = await renderApp('/playground')

    const draft = await screen.findByPlaceholderText(/Type a message/)
    fireEvent.change(draft, { target: { value: 'my unsent draft' } })
    fireEvent.change(screen.getByLabelText('System prompt'), { target: { value: 'be brief' } })
    fireEvent.click(screen.getByRole('switch', { name: 'Thinking mode' }))
    fireEvent.click(screen.getByRole('switch', { name: 'Web search' }))

    setLang('zh')

    expect(screen.getByText('思考模式')).toBeTruthy()
    expect(screen.getByPlaceholderText(/输入消息/)).toHaveProperty('value', 'my unsent draft')
    expect(screen.getByLabelText('System 提示')).toHaveProperty('value', 'be brief')
    expect(screen.getByRole('switch', { name: '思考模式' }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByRole('switch', { name: '联网搜索' }).getAttribute('aria-checked')).toBe('true')
  })

  it('updates the language without a full remount of the shell', async () => {
    const { setLang } = await renderApp('/settings')
    await waitFor(() => expect(screen.getAllByText('Settings').length).toBeGreaterThan(0))
    const sidebar = screen.getByRole('complementary')

    setLang('zh')

    // Same DOM node: the shell re-rendered rather than being recreated.
    expect(screen.getByRole('complementary')).toBe(sidebar)
    expect(screen.getAllByText('设置').length).toBeGreaterThan(0)
  })
})
