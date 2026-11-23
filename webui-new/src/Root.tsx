import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/toaster'
import { App } from './App'

/** Top-level tree rendered by main.tsx (and by tests). */
export function Root() {
  return (
    <TooltipProvider delayDuration={200}>
      <App />
      <Toaster />
    </TooltipProvider>
  )
}
