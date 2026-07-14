import { useMemo } from 'react'

import type { Cell } from '@/lib/api'
import type { Sheet } from '@/lib/sheet'

/**
 * The sheet with the detected grid drawn over it, each cell labelled with the
 * character the layout assigns to it.
 *
 * This is where a bad layout becomes obvious *before* slicing: the label sits on
 * the tile it claims, so a shifted row shows up as an 'A' floating over an 'N'.
 */
export function SheetView({
  preview,
  dims,
  cells,
  sheet,
}: {
  preview: string | null
  dims: { width: number; height: number } | null
  cells: Cell[]
  sheet: Sheet
}) {
  const chars = useMemo(() => sheet.layout.join(''), [sheet.layout])

  if (!preview || !dims) return null

  return (
    <div className="mx-auto max-w-6xl">
      <div className="relative overflow-hidden rounded-lg border bg-black">
        <svg
          viewBox={`0 0 ${dims.width} ${dims.height}`}
          className="block h-auto w-full"
        >
          <image href={preview} x={0} y={0} width={dims.width} height={dims.height} />

          {cells.map((c) => {
            const index = c.row * sheet.cols + c.col
            const ch = chars[index]
            const empty = !ch || ch === ' '

            return (
              <g key={index}>
                <rect
                  x={c.x}
                  y={c.y}
                  width={c.w}
                  height={c.h}
                  fill="none"
                  stroke={empty ? '#71717a' : '#e8563a'}
                  strokeWidth={2}
                  strokeDasharray={empty ? '6 6' : undefined}
                  opacity={0.9}
                />
                {!empty && (
                  <>
                    <rect
                      x={c.x}
                      y={c.y}
                      width={26}
                      height={20}
                      fill="#e8563a"
                      opacity={0.95}
                    />
                    <text
                      x={c.x + 13}
                      y={c.y + 15}
                      fill="#fff"
                      fontSize={14}
                      fontWeight={600}
                      textAnchor="middle"
                      fontFamily="ui-monospace, monospace"
                    >
                      {ch}
                    </text>
                  </>
                )}
              </g>
            )
          })}
        </svg>
      </div>

      <p className="mt-3 text-center text-xs text-muted-foreground">
        {dims.width} × {dims.height}
        {cells.length > 0 && ` · ${sheet.rows} × ${sheet.cols} grid · ${cells.length} cells`}
      </p>
    </div>
  )
}
