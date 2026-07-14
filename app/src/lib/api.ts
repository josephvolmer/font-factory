export type Cell = { row: number; col: number; x: number; y: number; w: number; h: number }
export type Glyph = {
  char: string
  name: string
  index: number
  row: number
  col: number
  image: string | null
}

declare global {
  interface Window {
    fontfactory: {
      call: (method: string, params: unknown) => Promise<{ ok: boolean; result?: any; error?: string }>
      openSheet: () => Promise<string | null>
      saveFile: (opts: { defaultPath?: string; filters?: { name: string; extensions: string[] }[] }) => Promise<string | null>
      showItem: (path: string) => Promise<void>
      onLog: (cb: (line: string) => void) => () => void
    }
  }
}

/** Unwraps the main process's {ok, result|error} envelope into a promise. */
async function call<T>(method: string, params: unknown = {}): Promise<T> {
  const res = await window.fontfactory.call(method, params)
  if (!res.ok) throw new Error(res.error || 'unknown error')
  return res.result as T
}

export const api = {
  probeSheet: (image: string) =>
    call<{ width: number; height: number; preview: string }>('probe_sheet', { image }),

  detectGrid: (toml: string, configPath: string) =>
    call<{ rows: number; cols: number; cells: Cell[] }>('detect_grid', {
      toml,
      config_path: configPath,
    }),

  slice: (toml: string, configPath: string) =>
    call<{ glyphs: Glyph[] }>('slice', { toml, config_path: configPath }),

  build: (toml: string, configPath: string) =>
    call<{ font: string; coverage: string[] }>('build', {
      toml,
      config_path: configPath,
    }),

  saveFont: (font: string, output: string) =>
    call<{ output: string }>('save_font', { font, output }),

  render: (p: { font: string; text: string; size: number; color: string; bg: string | null }) =>
    call<{ image: string }>('render', p),

  saveRender: (p: {
    font: string
    text: string
    size: number
    color: string
    bg: string | null
    output: string
  }) => call<{ output: string }>('save_render', p),
}
