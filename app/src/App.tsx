import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  Check,
  FileImage,
  Download,
  FolderOpen,
  Grid3x3,
  Hammer,
  Loader2,
  Save,
  Type,
} from 'lucide-react'
import { toast, Toaster } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'

import { api, type Cell, type Glyph } from '@/lib/api'
import { PRESETS, type Sheet, declaredChars, defaultSheet, toToml } from '@/lib/sheet'

import { GlyphGrid } from '@/components/GlyphGrid'
import { LayoutEditor } from '@/components/LayoutEditor'
import { SheetView } from '@/components/SheetView'

export default function App() {
  const [sheet, setSheet] = useState<Sheet | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [dims, setDims] = useState<{ width: number; height: number } | null>(null)

  const [cells, setCells] = useState<Cell[]>([])
  const [glyphs, setGlyphs] = useState<Glyph[]>([])
  const [gridError, setGridError] = useState<string | null>(null)

  const [font, setFont] = useState<string | null>(null)
  const [glyphCount, setGlyphCount] = useState(0)

  const [busy, setBusy] = useState<string | null>(null)
  const [tab, setTab] = useState('sheet')

  // Text-preview panel
  const [text, setText] = useState('Ransom Note\nabcdefghij')
  const [size, setSize] = useState(96)
  const [rendered, setRendered] = useState<string | null>(null)

  const update = useCallback(
    (patch: Partial<Sheet>) => setSheet((s) => (s ? { ...s, ...patch } : s)),
    []
  )

  async function openSheet() {
    const image = await window.fontfactory.openSheet()
    if (!image) return

    setBusy('Reading sheet')
    try {
      const info = await api.probeSheet(image)
      const configPath = image.replace(/\.[^.]+$/, '.toml')
      setSheet(defaultSheet(image, configPath))
      setPreview(info.preview)
      setDims({ width: info.width, height: info.height })
      setCells([])
      setGlyphs([])
      setFont(null)
      setGridError(null)
      setTab('sheet')
    } catch (e) {
      toast.error(String(e))
    } finally {
      setBusy(null)
    }
  }

  // Re-slicing is the fast feedback loop: any change to the grid or ink settings
  // should immediately show whether each glyph landed under the right character.
  const runSlice = useCallback(async () => {
    if (!sheet) return
    setBusy('Slicing')
    setGridError(null)
    try {
      const toml = toToml(sheet)
      const [grid, sliced] = await Promise.all([
        api.detectGrid(toml, sheet.configPath),
        api.slice(toml, sheet.configPath),
      ])
      setCells(grid.cells)
      setGlyphs(sliced.glyphs)
    } catch (e) {
      setGridError(String(e instanceof Error ? e.message : e))
      setCells([])
      setGlyphs([])
    } finally {
      setBusy(null)
    }
  }, [sheet])

  async function build() {
    if (!sheet) return
    setBusy('Building font')
    try {
      const res = await api.build(toToml(sheet), sheet.configPath)
      setFont(res.font)
      setGlyphCount(res.coverage.length)
      setTab('font')
      toast.success(`Built ${sheet.family}`, {
        description: `${res.coverage.length} glyphs · save it to keep it`,
      })
    } catch (e) {
      toast.error('Build failed', {
        description: String(e instanceof Error ? e.message : e),
      })
    } finally {
      setBusy(null)
    }
  }

  // Live text preview, debounced so typing doesn't spam the backend.
  useEffect(() => {
    if (!font) return
    const t = setTimeout(async () => {
      try {
        const res = await api.render({
          font,
          text,
          size,
          color: 'white',
          bg: null,
        })
        setRendered(res.image)
      } catch {
        /* a partial edit can be unrenderable; keep the last good image */
      }
    }, 220)
    return () => clearTimeout(t)
  }, [font, text, size])

  async function saveFont() {
    if (!font || !sheet) return
    const output = await window.fontfactory.saveFile({
      defaultPath: `${sheet.family}-${sheet.style}.ttf`,
      filters: [{ name: 'TrueType font', extensions: ['ttf'] }],
    })
    if (!output) return

    try {
      await api.saveFont(font, output)
      toast.success('Saved', {
        description: output,
        action: { label: 'Reveal', onClick: () => window.fontfactory.showItem(output) },
      })
    } catch (e) {
      toast.error('Could not save', {
        description: String(e instanceof Error ? e.message : e),
      })
    }
  }

  async function saveRender() {
    if (!font) return
    const output = await window.fontfactory.saveFile({
      defaultPath: 'specimen.png',
      filters: [{ name: 'PNG', extensions: ['png'] }],
    })
    if (!output) return
    await api.saveRender({ font, text, size, color: 'black', bg: 'white', output })
    toast.success('Saved', {
      action: { label: 'Reveal', onClick: () => window.fontfactory.showItem(output) },
    })
  }

  const expected = sheet ? declaredChars(sheet).length : 0
  const found = glyphs.filter((g) => g.image).length
  const missing = glyphs.filter((g) => !g.image)

  const layoutMismatch = useMemo(() => {
    if (!sheet) return null
    const bad = sheet.layout.findIndex((r) => r.length !== sheet.cols)
    if (sheet.layout.length !== sheet.rows) {
      return `Layout has ${sheet.layout.length} rows but the grid is ${sheet.rows}.`
    }
    if (bad >= 0) {
      return `Row ${bad + 1} has ${sheet.layout[bad].length} characters but the grid is ${sheet.cols} wide.`
    }
    return null
  }, [sheet])

  return (
    <div className="flex h-screen flex-col bg-background">
      <Toaster theme="dark" position="bottom-right" richColors />

      <header className="drag flex h-14 shrink-0 items-center justify-between border-b px-5 pl-20">
        <div className="flex items-center gap-2.5">
          <Type className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold tracking-tight">Font Factory</span>
          {sheet && (
            <span className="ml-1 text-sm text-muted-foreground">
              {sheet.imagePath.split('/').pop()}
            </span>
          )}
        </div>

        <div className="no-drag flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={openSheet}>
            <FolderOpen /> Open sheet
          </Button>
          <Button size="sm" onClick={build} disabled={!sheet || !!busy || !!layoutMismatch}>
            {busy === 'Building font' ? <Loader2 className="animate-spin" /> : <Hammer />}
            Build font
          </Button>
        </div>
      </header>

      {!sheet ? (
        <Empty onOpen={openSheet} />
      ) : (
        <div className="flex min-h-0 flex-1">
          <Sidebar
            sheet={sheet}
            update={update}
            onSlice={runSlice}
            busy={busy}
            layoutMismatch={layoutMismatch}
          />

          <main className="flex min-w-0 flex-1 flex-col">
            <div className="flex items-center justify-between border-b px-5 py-2.5">
              <Tabs value={tab} onValueChange={setTab}>
                <TabsList>
                  <TabsTrigger value="sheet">
                    <FileImage /> Sheet
                  </TabsTrigger>
                  <TabsTrigger value="glyphs">
                    <Grid3x3 /> Glyphs
                    {glyphs.length > 0 && (
                      <Badge
                        variant={missing.length ? 'destructive' : 'secondary'}
                        className="ml-1"
                      >
                        {found}/{expected}
                      </Badge>
                    )}
                  </TabsTrigger>
                  <TabsTrigger value="font" disabled={!font}>
                    <Type /> Font
                  </TabsTrigger>
                </TabsList>
              </Tabs>

              <Status
                busy={busy}
                gridError={gridError}
                layoutMismatch={layoutMismatch}
                missing={missing.length}
                cells={cells.length}
              />
            </div>

            <div className="min-h-0 flex-1 overflow-auto p-5">
              {tab === 'sheet' && (
                <SheetView preview={preview} dims={dims} cells={cells} sheet={sheet} />
              )}

              {tab === 'glyphs' && (
                <GlyphGrid glyphs={glyphs} cols={sheet.cols} onSlice={runSlice} busy={!!busy} />
              )}

              {tab === 'font' && font && (
                <FontPanel
                  font={font}
                  family={sheet.family}
                  glyphCount={glyphCount}
                  text={text}
                  setText={setText}
                  size={size}
                  setSize={setSize}
                  rendered={rendered}
                  onSaveFont={saveFont}
                  onSavePng={saveRender}
                />
              )}
            </div>
          </main>
        </div>
      )}
    </div>
  )
}

function Status({
  busy,
  gridError,
  layoutMismatch,
  missing,
  cells,
}: {
  busy: string | null
  gridError: string | null
  layoutMismatch: string | null
  missing: number
  cells: number
}) {
  // The Build button shows its own spinner, so echoing "Building font…" here
  // would be two indicators for one operation. Slicing has no button of its own,
  // so it does report here.
  if (busy && busy !== 'Building font') {
    return (
      <span className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> {busy}…
      </span>
    )
  }
  if (busy === 'Building font') return null
  if (layoutMismatch) {
    return (
      <span className="flex items-center gap-2 text-sm text-destructive">
        <AlertTriangle className="h-3.5 w-3.5" /> {layoutMismatch}
      </span>
    )
  }
  if (gridError) {
    return (
      <span className="flex max-w-xl items-center gap-2 truncate text-sm text-destructive">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
        {gridError.split('\n')[0]}
      </span>
    )
  }
  if (missing > 0) {
    return (
      <span className="flex items-center gap-2 text-sm text-destructive">
        <AlertTriangle className="h-3.5 w-3.5" /> {missing} glyph
        {missing === 1 ? '' : 's'} not found
      </span>
    )
  }
  if (cells > 0) {
    return (
      <span className="flex items-center gap-2 text-sm text-muted-foreground">
        <Check className="h-3.5 w-3.5 text-primary" /> {cells} cells
      </span>
    )
  }
  return null
}

function Empty({ onOpen }: { onOpen: () => void }) {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-xl border bg-card">
          <Type className="h-6 w-6 text-primary" />
        </div>
        <h2 className="mb-1.5 text-lg font-semibold">Open a glyph sheet</h2>
        <p className="mb-6 text-sm leading-relaxed text-muted-foreground">
          A grid of hand-made letters — one tile per character. Tell the app what
          order they are in, and it will slice, trace and assemble them into an
          installable font.
        </p>
        <Button onClick={onOpen}>
          <FolderOpen /> Choose an image
        </Button>
      </div>
    </div>
  )
}

function Sidebar({
  sheet,
  update,
  onSlice,
  busy,
  layoutMismatch,
}: {
  sheet: Sheet
  update: (p: Partial<Sheet>) => void
  onSlice: () => void
  busy: string | null
  layoutMismatch: string | null
}) {
  // Re-slice automatically when a setting that affects segmentation changes.
  const first = useRef(true)
  useEffect(() => {
    if (first.current) {
      first.current = false
      onSlice()
      return
    }
    if (layoutMismatch) return
    const t = setTimeout(onSlice, 350)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    sheet.rows,
    sheet.cols,
    sheet.layout.join('\n'),
    sheet.background,
    sheet.ignoreTop,
    sheet.pad,
    sheet.polarity,
    sheet.isolate,
  ])

  return (
    <aside className="w-[340px] shrink-0 overflow-y-auto border-r">
      <div className="space-y-5 p-5">
        <Section title="Font">
          <Field label="Family">
            <Input
              value={sheet.family}
              onChange={(e) => update({ family: e.target.value })}
            />
          </Field>
          <Field label="Style">
            <Input value={sheet.style} onChange={(e) => update({ style: e.target.value })} />
          </Field>
        </Section>

        <Separator />

        <Section title="Layout">
          <Field label="Preset">
            <Select
              onValueChange={(k) => {
                const p = PRESETS[k]
                if (p) update({ rows: p.rows, cols: p.cols, layout: [...p.layout] })
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="Choose a preset…" />
              </SelectTrigger>
              <SelectContent>
                {Object.keys(PRESETS).map((k) => (
                  <SelectItem key={k} value={k}>
                    {k}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <LayoutEditor sheet={sheet} update={update} error={layoutMismatch} />
        </Section>

        <Separator />

        <Section title="Segmentation">
          <Field label="Tiles are">
            <Select
              value={sheet.background}
              onValueChange={(v) => update({ background: v as Sheet['background'] })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Detect automatically</SelectItem>
                <SelectItem value="dark">Brighter than the background</SelectItem>
                <SelectItem value="light">Darker than the background</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field label="Ink">
            <Select
              value={sheet.polarity}
              onValueChange={(v) => update({ polarity: v as Sheet['polarity'] })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Per tile (mixed sheet)</SelectItem>
                <SelectItem value="dark_on_light">Dark on light</SelectItem>
                <SelectItem value="light_on_dark">Light on dark</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Row label="Skip top" value={`${sheet.ignoreTop}px`}>
            <Slider
              value={[sheet.ignoreTop]}
              min={0}
              max={300}
              step={5}
              onValueChange={([v]) => update({ ignoreTop: v })}
            />
          </Row>

          <Row label="Tile inset" value={`${sheet.pad}px`}>
            <Slider
              value={[sheet.pad]}
              min={0}
              max={20}
              step={1}
              onValueChange={([v]) => update({ pad: v })}
            />
          </Row>

          <div className="flex items-center justify-between pt-1">
            <div>
              <Label className="normal-case tracking-normal text-foreground">
                Isolate letter
              </Label>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Drop bleed-in from neighbouring tiles
              </p>
            </div>
            <Switch
              checked={sheet.isolate}
              onCheckedChange={(v) => update({ isolate: v })}
            />
          </div>
        </Section>

        <Separator />

        <Section title="Proportions">
          <Row label="Cap height" value={String(sheet.capHeight)}>
            <Slider
              value={[sheet.capHeight]}
              min={400}
              max={900}
              step={10}
              onValueChange={([v]) => update({ capHeight: v })}
            />
          </Row>

          <Row label="x-height" value={String(sheet.xHeight)}>
            <Slider
              value={[sheet.xHeight]}
              min={300}
              max={sheet.capHeight}
              step={10}
              onValueChange={([v]) => update({ xHeight: v })}
            />
          </Row>
          <p className="-mt-1 text-xs leading-relaxed text-muted-foreground">
            Every tile is the same size, so lowercase arrives as tall as uppercase.
            Set x-height equal to cap height for a sheet with no lowercase.
          </p>

          <Row label="Letter spacing" value={String(sheet.sideBearing)}>
            <Slider
              value={[sheet.sideBearing]}
              min={0}
              max={150}
              step={5}
              onValueChange={([v]) => update({ sideBearing: v })}
            />
          </Row>

          <Row label="Word space" value={String(sheet.spaceWidth)}>
            <Slider
              value={[sheet.spaceWidth]}
              min={100}
              max={600}
              step={10}
              onValueChange={([v]) => update({ spaceWidth: v })}
            />
          </Row>
        </Section>
      </div>
    </aside>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h3>
      {children}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  )
}

function Row({
  label,
  value,
  children,
}: {
  label: string
  value: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label>{label}</Label>
        <span className="font-mono text-xs text-muted-foreground">{value}</span>
      </div>
      {children}
    </div>
  )
}

function FontPanel({
  font,
  family,
  glyphCount,
  text,
  setText,
  size,
  setSize,
  rendered,
  onSaveFont,
  onSavePng,
}: {
  font: string
  family: string
  glyphCount: number
  text: string
  setText: (v: string) => void
  size: number
  setSize: (v: number) => void
  rendered: string | null
  onSaveFont: () => void
  onSavePng: () => void
}) {
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      {/* The built font lives in a temp directory, so its path is not shown: it is
          not a location the user can meaningfully act on, and surfacing it invites
          them to treat scratch space as somewhere their work is kept. Saving is
          the only way a font leaves the app. */}
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle className="text-base">{family}</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {glyphCount} glyphs · not saved yet
            </p>
          </div>
          <Button size="sm" onClick={onSaveFont}>
            <Download /> Save font…
          </Button>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Try it</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            className="font-mono text-sm"
          />

          <div className="flex items-center gap-4">
            <Label className="shrink-0">Size</Label>
            <Slider
              value={[size]}
              min={24}
              max={220}
              step={2}
              onValueChange={([v]) => setSize(v)}
              className="flex-1"
            />
            <span className="w-12 shrink-0 text-right font-mono text-xs text-muted-foreground">
              {size}px
            </span>
            <Button variant="outline" size="sm" onClick={onSavePng}>
              <Save /> Save PNG
            </Button>
          </div>

          <div className="flex min-h-[180px] items-center justify-center overflow-auto rounded-lg border bg-secondary/30 p-6">
            {rendered ? (
              <img src={rendered} alt="" className="max-w-full" />
            ) : (
              <span className="text-sm text-muted-foreground">Type to preview</span>
            )}
          </div>
        </CardContent>
      </Card>

    </div>
  )
}
