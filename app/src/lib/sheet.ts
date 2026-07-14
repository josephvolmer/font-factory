/**
 * The editable state of one sheet, and how it becomes a TOML config.
 *
 * The Python side owns config validation, so the UI does not re-implement those
 * rules — it serialises to TOML and lets the loader complain. That keeps a single
 * definition of what a valid sheet is, including the layout row/column check that
 * catches a misaligned grid before it silently mislabels every glyph.
 */

export type Sheet = {
  imagePath: string
  configPath: string

  family: string
  style: string
  version: string

  rows: number
  cols: number
  layout: string[] // one string per row

  background: 'auto' | 'dark' | 'light'
  ignoreTop: number
  pad: number

  polarity: 'auto' | 'dark_on_light' | 'light_on_dark'
  isolate: boolean

  upscale: number
  alphamax: number
  turdsize: number

  capHeight: number
  xHeight: number
  sideBearing: number
  spaceWidth: number
  descenderDrop: number
}

export const PRESETS: Record<string, { rows: number; cols: number; layout: string[] }> = {
  'Full ASCII + symbols (8 × 13)': {
    rows: 8,
    cols: 13,
    layout: [
      'ABCDEFGHIJKLM',
      'NOPQRSTUVWXYZ',
      'abcdefghijklm',
      'nopqrstuvwxyz',
      '0123456789.,!',
      '?\'";:(){}[]@&',
      '#$%^*+=_-<>/\\',
      '|~`€£¥¢©®™÷±×',
    ],
  },
  'Letters + digits (7 × 9)': {
    rows: 7,
    cols: 9,
    layout: [
      'ABCDEFGHI',
      'JKLMNOPQR',
      'STUVWXYZa',
      'bcdefghij',
      'klmnopqrs',
      'tuvwxyz01',
      '23456789 ',
    ],
  },
  'Uppercase + digits (5 × 8)': {
    rows: 5,
    cols: 8,
    layout: ['ABCDEFGH', 'IJKLMNOP', 'QRSTUVWX', 'YZ012345', '6789.,!?'],
  },
  'Uppercase only (4 × 7)': {
    rows: 4,
    cols: 7,
    layout: ['ABCDEFG', 'HIJKLMN', 'OPQRSTU', 'VWXYZ  '],
  },
}

export function defaultSheet(imagePath: string, configPath: string): Sheet {
  const preset = PRESETS['Full ASCII + symbols (8 × 13)']
  const stem = imagePath.split('/').pop()?.replace(/\.[^.]+$/, '') || 'MyFont'
  const family = stem
    .split(/[-_\s]+/)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('')

  return {
    imagePath,
    configPath,
    family: family || 'MyFont',
    style: 'Regular',
    version: '1.0',
    rows: preset.rows,
    cols: preset.cols,
    layout: [...preset.layout],
    background: 'auto',
    ignoreTop: 0,
    pad: 3,
    polarity: 'auto',
    isolate: true,
    upscale: 4,
    alphamax: 1.0,
    turdsize: 8,
    capHeight: 700,
    xHeight: 500,
    sideBearing: 40,
    spaceWidth: 260,
    descenderDrop: 150,
  }
}

/** TOML needs backslashes and quotes escaped inside a basic multi-line string. */
function escapeLayoutLine(line: string): string {
  return line.replace(/\\/g, '\\\\')
}

export function toToml(s: Sheet): string {
  const layout = s.layout.map(escapeLayoutLine).join('\n')

  return `[font]
family  = "${s.family}"
style   = "${s.style}"
version = "${s.version}"

[sheet]
image = "${s.imagePath}"
rows  = ${s.rows}
cols  = ${s.cols}
layout = """
${layout}
"""

[sheet.grid]
mode       = "auto"
background = "${s.background}"
ignore_top = ${s.ignoreTop}
pad        = ${s.pad}

[ink]
polarity = "${s.polarity}"
isolate  = ${s.isolate}

[trace]
upscale      = ${s.upscale}
alphamax     = ${s.alphamax}
opttolerance = 0.2
turdsize     = ${s.turdsize}

[metrics]
cap_height     = ${s.capHeight}
x_height       = ${s.xHeight}
side_bearing   = ${s.sideBearing}
space_width    = ${s.spaceWidth}
descender_drop = ${s.descenderDrop}

[output]
dir = "fonts"
`
}

/** Characters the layout declares, ignoring the spaces that mark empty cells. */
export function declaredChars(s: Sheet): string[] {
  return s.layout.join('').split('').filter((c) => c !== ' ')
}
