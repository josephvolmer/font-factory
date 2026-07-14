import { AlertTriangle, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { Glyph } from '@/lib/api'
import { cn } from '@/lib/utils'

/**
 * Every sliced glyph, shown beneath the character it was filed as.
 *
 * This is the single most important view in the app, and it earns that by being
 * the only cheap way to catch a misaligned grid. A layout that is off by one cell
 * still slices cleanly, still reports the expected glyph count, and produces a
 * font in which every letter is the wrong letter. The count says 104/104; only
 * the picture says the 'A' is actually an 'N'.
 */
export function GlyphGrid({
  glyphs,
  cols,
  onSlice,
  busy,
}: {
  glyphs: Glyph[]
  cols: number
  onSlice: () => void
  busy: boolean
}) {
  if (!glyphs.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
        <p className="max-w-sm text-sm text-muted-foreground">
          No glyphs yet. Check the grid settings, then slice.
        </p>
        <Button variant="outline" onClick={onSlice} disabled={busy}>
          <RefreshCw className={cn(busy && 'animate-spin')} /> Slice
        </Button>
      </div>
    )
  }

  const missing = glyphs.filter((g) => !g.image).length

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Each glyph is shown under the character it was filed as.{' '}
          <span className="text-foreground">
            Check that they match before building
          </span>{' '}
          — a grid that is off by one cell still slices cleanly and still produces
          the right count, but every letter comes out wrong.
        </p>
        <Button variant="outline" size="sm" onClick={onSlice} disabled={busy}>
          <RefreshCw className={cn('h-3.5 w-3.5', busy && 'animate-spin')} /> Re-slice
        </Button>
      </div>

      {missing > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />
          <span>
            {missing} tile{missing === 1 ? '' : 's'} produced no ink. The grid may be
            misaligned, or the ink polarity may be wrong for those tiles.
          </span>
        </div>
      )}

      <div
        className="grid gap-1.5"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
      >
        {glyphs.map((g) => (
          <div
            key={g.index}
            className={cn(
              'group overflow-hidden rounded-md border bg-card transition-colors',
              !g.image && 'border-destructive/50 bg-destructive/5'
            )}
          >
            <div className="flex h-[86px] items-center justify-center p-2">
              {g.image ? (
                <img
                  src={g.image}
                  alt={g.char}
                  className="glyph-invert max-h-full max-w-full object-contain"
                />
              ) : (
                <AlertTriangle className="h-4 w-4 text-destructive" />
              )}
            </div>
            <div
              className={cn(
                'border-t px-1.5 py-1 text-center',
                g.image ? 'bg-secondary/50' : 'bg-destructive/10'
              )}
            >
              <span className="font-mono text-xs text-muted-foreground">
                {g.char}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
