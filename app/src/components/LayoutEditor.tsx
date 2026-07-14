import { AlertTriangle } from 'lucide-react'

import { Label } from '@/components/ui/label'
import type { Sheet } from '@/lib/sheet'
import { cn } from '@/lib/utils'

/**
 * The character layout, edited as a visual block that mirrors the sheet: one line
 * per row of tiles, one character per column.
 *
 * Writing it this way rather than as a flat string is the whole point — a flat
 * list of characters gives no clue when it has drifted out of step with the
 * artwork, which is exactly how a sheet ends up with its lowercase silently
 * missing and every glyph filed one row late. Here a wrong-length row is visible,
 * and is flagged before it can reach the slicer.
 */
export function LayoutEditor({
  sheet,
  update,
  error,
}: {
  sheet: Sheet
  update: (p: Partial<Sheet>) => void
  error: string | null
}) {
  const value = sheet.layout.join('\n')

  function onChange(text: string) {
    const lines = text.split('\n')
    update({
      layout: lines,
      rows: lines.length,
      cols: Math.max(...lines.map((l) => l.length), 1),
    })
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label>Characters, row by row</Label>
        <span className="font-mono text-xs text-muted-foreground">
          {sheet.rows} × {sheet.cols}
        </span>
      </div>

      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        rows={sheet.layout.length + 1}
        className={cn(
          'w-full resize-y rounded-md border bg-transparent p-2.5 font-mono text-sm leading-relaxed tracking-[0.18em] shadow-sm',
          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
          error ? 'border-destructive' : 'border-input'
        )}
      />

      {error ? (
        <p className="flex items-start gap-1.5 text-xs text-destructive">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          {error}
        </p>
      ) : (
        <p className="text-xs leading-relaxed text-muted-foreground">
          One line per row of tiles. Use a space for an empty cell.
        </p>
      )}
    </div>
  )
}
