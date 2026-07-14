# Font Factory

Turns a glyph sheet — a grid of hand-made letters — into an installable `.ttf`.

```
sheets/magazine.png   +   sheets/magazine.toml   ->   MagazineCutout-Regular.ttf
   the artwork              what's on it                     the font
```

Two front ends over one pipeline: a CLI, where a sheet is described by a config
file, and a desktop app, where you point at an image and adjust by eye.

## Install

```sh
pip install -r requirements.txt
```

That is the whole dependency list — no potrace binary, no FontForge. The pipeline
is pure Python: `potracer` (a pure-Python port of potrace) for tracing, `fontTools`
for assembly. Nothing to install with a package manager, and nothing that breaks
when it moves to another machine.

## Build a font

```sh
./fontfactory.py build sheets/magazine.toml     # or: make magazine
make all                                        # every sheet in sheets/
make list                                       # what sheets exist
```

## Run the app

```sh
cd app
npm install
npm run dev
```

Open a sheet, set the character layout, hit **Build font**. The font is built into
a temp directory and lives only there until you **Save** it — the app never writes
into this repo.

> The app runs from source. Packaging it into a distributable `.app`/`.dmg` is not
> wired up yet: it needs a bundled, relocatable Python runtime, which is the whole
> reason the pipeline has no system binaries in the first place.

## Add a new sheet

```sh
./fontfactory.py new sheets/mysheet.toml --image sheets/mysheet.png --rows 6 --cols 10
# edit the `layout` block to match your artwork
./fontfactory.py contact sheets/mysheet.toml    # LOOK AT THIS before building
./fontfactory.py build   sheets/mysheet.toml
```

**Check the contact sheet.** It renders every sliced glyph beneath the name it was
filed under. A layout that is off by one cell still builds cleanly, still reports
the right glyph count, and is completely wrong — a picture is the only cheap way
to catch it. (Not hypothetical: the first version of this pipeline shipped a font
where `A` contained an **N**, and the entire lowercase alphabet was missing.)

## The config

`layout` is the map from tiles to characters, written as a visual block that
mirrors the sheet — one line per row, one character per column, read left to
right. A space marks an intentionally empty cell. It is checked against
`rows`/`cols`, and the build refuses to start if they disagree.

```toml
[font]
family  = "MagazineCutout"
style   = "Regular"

[sheet]
image = "magazine.png"
rows  = 8
cols  = 13
layout = """
ABCDEFGHIJKLM
NOPQRSTUVWXYZ
abcdefghijklm
nopqrstuvwxyz
0123456789.,!
?'";:(){}[]@&
#$%^*+=_-<>/\\
|~`€£¥¢©®™÷±×
"""
```

Everything else has a working default. The keys worth knowing:

| key | when to touch it |
|---|---|
| `sheet.grid.background` | `dark` if the tiles are brighter than the gaps between them, `light` if darker. `auto` reads the image border. Get this wrong and the whole sheet reads as one blob. |
| `sheet.grid.ignore_top` | Pixels to skip at the top, for a sheet with a title bar. |
| `sheet.grid.mode` | `fixed` + `left/top/right/bottom` when auto-detection can't find the grid. |
| `ink.polarity` | `auto` decides per tile — necessary when the polarity flips across the sheet. Pin to `dark_on_light` / `light_on_dark` for a uniform one. |
| `metrics.x_height` | Set equal to `cap_height` for a sheet with no lowercase, or one whose lowercase shouldn't be smaller. |
| `metrics.side_bearing` | Letter spacing. |

The app does not read these files. It builds the same config in memory from the
UI and hands it to the same loader, so both front ends share one definition of
what a valid sheet is — including the layout check.

## Inspect

```sh
./fontfactory.py contact sheets/magazine.toml               # is each glyph filed right?
./fontfactory.py verify  fonts/MagazineCutout-Regular.ttf --config sheets/magazine.toml
./fontfactory.py proof   fonts/MagazineCutout-Regular.ttf   # specimen text
./fontfactory.py build   sheets/magazine.toml --stage slice --debug   # grid overlay + tile mask
```

`verify` checks the font's tables rather than trusting that it rendered: full
character coverage against the sheet, no empty outlines, nothing built upside
down.

`proof` renders a fixed specimen chosen to expose the failure modes below —
stacked alphabet rows show small-caps, `typing jumpy quags` packs every descender,
`"Pay up," he said;` packs the raised marks. It filters itself to the font's actual
coverage, so a sheet with no lowercase proofs as the font it is rather than as a
wall of `.notdef` boxes.

## Render text

```sh
./fontfactory.py render fonts/MagazineCutout-Regular.ttf \
    --text input.txt --output output.png --size 96 --color black --bg white

./fontfactory.py render fonts/MagazineCutout-Regular.ttf \
    --string 'Pay\nup' --output ransom.png --color '#cc2200'   # --bg omitted: transparent
```

Or `make render FONT=... TEXT=... COLOR=... BG=...` (`BG=` for transparent).

## How it works

**slice** — Finds the grid by projecting the gaps between tiles rather than
dividing the image into equal cells, because hand-made sheets don't sit on an
exact lattice. Then, per tile, it decides which pixels are ink. That decision is
made *per tile* because a ransom-note sheet's polarity flips (white-on-red beside
black-on-cream) and no global threshold can read both. Finally it keeps the
largest connected blob that doesn't touch the tile border — neighbouring tiles
bleed a strip into every crop, and only the letter clears the edge. Interior marks
(the dot on `i`, both dots of `:`) are re-attached by column overlap.

**vectorize** — Upscales 4× and traces. The upscale matters: tracing an 80px glyph
directly renders a torn paper edge as visible facets. Outlines are stored y-up, in
the orientation a font wants, so nothing downstream has to flip them.

**assemble** — Scales and positions the outlines. Three things here are *not*
inherited from the artwork and have to be imposed. Each one is a bug if you skip
it, and each produces a font that looks plausible until you look closely:

- **Scale.** Every tile is the same size, so a lowercase `a` arrives exactly as
  tall as a capital `A`. One global scale gives you small-caps. Uppercase keys to
  cap-height, lowercase to x-height, ascenders in between.
- **Baseline.** Each glyph is cut as its own tile, so the sheet carries no baseline
  at all. Every glyph is grounded, then descenders (`g j p q y , ;`) are dropped
  and hanging marks (quotes, `^`, `~`) lifted, by table in `[metrics]`.
- **Declared coverage.** `OS/2.ulCodePageRange1` must say the font supports Latin-1.
  Left at zero it means *"no code pages at all"*, and renderers that consult it
  will drop the currency and symbol glyphs — while a Pillow preview, which reads
  only the cmap, still shows them. A font that looks complete right up until it
  leaves the pipeline.

The vertical clipping box (`usWinAscent`/`usWinDescent`) is measured from the
outlines that actually exist, not from the nominal metrics, because a raised mark
can overshoot the ascent — the asterisk on the magazine sheet reaches 801 against
an ascent of 800, and would otherwise lose its top row of pixels.

## Layout

```
fontfactory/          the pipeline
  config.py           sheet config: load, validate, char <-> filename
  preview.py          contact sheet, proof, text rendering
  stages/
    slice.py          sheet -> per-glyph bitmaps
    vectorize.py      bitmaps -> traced outlines
    assemble.py       outlines -> ttf (fontTools)
  cli.py
app/                  Electron + React + shadcn
  electron/           main process; bridge to the python sidecar
  scripts/backend.py  JSON-RPC sidecar over the pipeline
  src/                renderer
sheets/               one .png + one .toml per font
fonts/                built .ttf (gitignored; `make all` regenerates)
build/<name>/         intermediates (gitignored)
```
