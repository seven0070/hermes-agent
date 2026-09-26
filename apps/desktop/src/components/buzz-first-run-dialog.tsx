import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

const KEY = 'hermes-buzz-first-run-choice-v1'

function previousChoice() {
  try { return window.localStorage.getItem(KEY) === 'done' } catch { return false }
}

function rememberChoice() {
  try { window.localStorage.setItem(KEY, 'done') } catch { /* non-persistent storage: leave the choice non-blocking */ }
}

/** Shown only after the owner finishes initial provider onboarding. */
export function BuzzFirstRunDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [error, setError] = useState<string | null>(null)
  if (!open) return null
  return (
    <Dialog open={open} onOpenChange={value => { if (!value) { rememberChoice(); onClose() } }}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Set up Buzz too?</DialogTitle>
          <DialogDescription>
            Optional local chat on this Windows PC. Buzz needs Docker Desktop, Rust, and its own desktop app. You can skip it and set it up later.
          </DialogDescription>
        </DialogHeader>
        {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
        <DialogFooter>
          <Button onClick={() => { rememberChoice(); onClose() }} variant="outline">Not now</Button>
          <Button onClick={async () => {
            try {
              const result = await window.hermesDesktop?.buzzLocalSetup?.launch()
              if (!result?.ok) { setError(result?.error || 'Buzz setup could not be opened'); return }
              rememberChoice()
              onClose()
            } catch { setError('Buzz setup could not be opened') }
          }}>Open setup</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function shouldOfferBuzzFirstRun(): boolean {
  return typeof window !== 'undefined' && !previousChoice() && Boolean(window.hermesDesktop?.buzzLocalSetup)
}
