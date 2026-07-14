"""Command line entry point.

    fontfactory build   sheets/magazine.toml
    fontfactory build   sheets/magazine.toml --stage slice --debug
    fontfactory contact sheets/magazine.toml
    fontfactory proof   fonts/MagazineCutout-Regular.ttf
    fontfactory render  fonts/MagazineCutout-Regular.ttf --text input.txt --bg white
    fontfactory verify  fonts/MagazineCutout-Regular.ttf --config sheets/magazine.toml
    fontfactory new     sheets/mysheet.toml --image sheets/mysheet.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config as config_mod
from . import preview
from .stages import assemble, slice as slice_stage, vectorize

STAGES = ("slice", "vectorize", "assemble")


def cmd_build(args) -> int:
    cfg = config_mod.load(args.config)

    if args.stage:
        wanted = STAGES[: STAGES.index(args.stage) + 1] if args.through else [args.stage]
    else:
        wanted = list(STAGES)

    print(f"{cfg.family}-{cfg.style}  <- {cfg.image.name}")

    if "slice" in wanted:
        slice_stage.run(cfg, debug=args.debug)
        if args.debug or args.contact:
            path = preview.contact_sheet(cfg)
            print(f"    contact sheet: {path}")

    if "vectorize" in wanted:
        vectorize.run(cfg, debug=args.debug)

    if "assemble" in wanted:
        ttf = assemble.run(cfg, debug=args.debug)
        if args.proof:
            out = cfg.build_dir / "proof.png"
            preview.proof(ttf, out)
            print(f"    proof: {out}")
        print(f"  -> {ttf}")

    return 0


def cmd_path(args) -> int:
    """Print the .ttf a config builds. Lets the Makefile clean without guessing."""
    cfg = config_mod.load(args.config)
    print(cfg.out_dir / cfg.font_filename)
    return 0


def cmd_contact(args) -> int:
    cfg = config_mod.load(args.config)
    if not (cfg.build_dir / "glyphs").exists():
        slice_stage.run(cfg)
    path = preview.contact_sheet(cfg)
    print(path)
    return 0


def cmd_proof(args) -> int:
    ttf = Path(args.font)
    if not ttf.exists():
        raise SystemExit(f"font not found: {ttf}")

    lines = None
    if args.text:
        lines = Path(args.text).read_text(encoding="utf-8").splitlines()

    out = Path(args.output) if args.output else ttf.with_suffix(".proof.png")
    preview.proof(ttf, out, lines=lines, size=args.size)
    print(out)
    return 0


def cmd_render(args) -> int:
    ttf = Path(args.font)
    if not ttf.exists():
        raise SystemExit(f"font not found: {ttf}")

    if args.text:
        lines = Path(args.text).read_text(encoding="utf-8").splitlines()
    elif args.string:
        lines = args.string.split("\\n")
    else:
        raise SystemExit("give --text <file> or --string <text>")

    out = preview.render(
        ttf,
        Path(args.output),
        lines,
        size=args.size,
        color=args.color,
        bg=args.bg,
        face_index=args.face,
    )
    print(out)
    return 0


def cmd_verify(args) -> int:
    """Check the built font's tables rather than trusting that it rendered."""
    from fontTools.ttLib import TTFont

    ttf = Path(args.font)
    if not ttf.exists():
        raise SystemExit(f"font not found: {ttf}")

    font = TTFont(str(ttf))
    cmap = font.getBestCmap()
    head, hhea = font["head"], font["hhea"]

    print(f"{ttf.name}")
    print(f"  glyphs       {font['maxp'].numGlyphs}")
    print(f"  cmap entries {len(cmap)}")
    print(f"  units/em     {head.unitsPerEm}")
    print(f"  ascent/desc  {hhea.ascent} / {hhea.descent}")

    # Sanity-check the shape of the outlines, not just their presence: a font can
    # have a full cmap and still be built upside down or flat.
    from fontTools.pens.boundsPen import BoundsPen

    glyphs = font.getGlyphSet()
    below, empty = [], []
    for ch, gname in sorted(cmap.items()):
        pen = BoundsPen(glyphs)
        glyphs[gname].draw(pen)
        if pen.bounds is None:
            if chr(ch) != " ":
                empty.append(chr(ch))
            continue
        if pen.bounds[3] <= 0:  # nothing above the baseline
            below.append(chr(ch))

    if empty:
        print(f"  empty        {''.join(empty)}")
    if below:
        print(f"  BELOW BASELINE {''.join(below)}  (outlines may be flipped)")

    # What should the font contain? Either an explicit character list, or the
    # sheet config itself, which is the real source of truth.
    want = None
    if args.expect:
        want = Path(args.expect).read_text(encoding="utf-8").replace("\n", "")
    elif args.config:
        want = config_mod.load(args.config).layout

    if want is not None:
        want = "".join(dict.fromkeys(c for c in want if c != " "))
        missing = [c for c in want if ord(c) not in cmap]
        if missing:
            print(f"  MISSING      {''.join(missing)}")
            return 1
        print(f"  coverage     all {len(want)} expected characters present")

    return 1 if (empty or below) else 0


TEMPLATE = '''\
# Sheet config for {name}.
#
# `layout` is the map from tiles to characters, written as a visual block: one
# line per row of the sheet, one character per column, read left to right. It
# must match `rows` and `cols` exactly. Use a space to mark an empty cell.
#
# Get this wrong and every glyph is filed under the wrong name, so check the
# contact sheet before trusting a build:
#
#     fontfactory contact {config}

[font]
family  = "{family}"
style   = "Regular"
version = "1.0"

[sheet]
image = "{image}"
rows  = {rows}
cols  = {cols}
layout = """
ABCDEFGHIJKLM
NOPQRSTUVWXYZ
abcdefghijklm
nopqrstuvwxyz
0123456789.,!
?'";:(){{}}[]@&
#$%^*+=_-<>/\\\\
|~`€£¥¢©®™÷±×
"""

# The grid is found by projecting the gaps between tiles. If detection fails,
# nudge these, or switch to mode = "fixed" and give explicit pixel bounds.
[sheet.grid]
mode       = "auto"
background = "auto"  # auto | dark | light -- are the tiles brighter or darker
                     # than the gaps between them? "auto" reads the image border.
ignore_top = 0       # pixels to ignore at the top (a title bar, say)
pad        = 3       # shave the tile edge before segmenting

[ink]
# "auto" decides per tile, which is what a sheet needs when its polarity flips
# (white-on-red beside black-on-cream). Force it if a uniform sheet misreads.
polarity = "auto"    # auto | dark_on_light | light_on_dark
isolate  = true      # drop strips bleeding in from neighbouring tiles

[trace]
upscale      = 4     # trace bigger; a small glyph traces to visible facets
alphamax     = 1.0   # lower = sharper corners
opttolerance = 0.2
turdsize     = 8     # drop specks smaller than this

[metrics]
cap_height     = 700  # capitals, in em units
x_height       = 500  # lowercase without ascenders; raise toward cap_height
                      # for a font whose lowercase should not be smaller
side_bearing   = 40   # letter spacing
space_width    = 260  # word gap
descender_drop = 150

[output]
dir = "fonts"
'''


def cmd_new(args) -> int:
    out = Path(args.config)
    if out.exists() and not args.force:
        raise SystemExit(f"{out} already exists (use --force to overwrite)")

    image = Path(args.image) if args.image else out.with_suffix(".png")
    try:
        rel = image.resolve().relative_to(out.resolve().parent)
        image_ref = str(rel)
    except ValueError:
        image_ref = str(image)

    family = args.family or "".join(
        part.capitalize() for part in out.stem.replace("-", "_").split("_")
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        TEMPLATE.format(
            name=out.stem,
            config=out,
            family=family,
            image=image_ref,
            rows=args.rows,
            cols=args.cols,
        ),
        encoding="utf-8",
    )

    print(f"wrote {out}")
    print(f"  1. put your sheet at {image}")
    print(f"  2. edit `layout` to match the sheet ({args.rows} rows x {args.cols} cols)")
    print(f"  3. fontfactory contact {out}      # confirm every glyph is filed right")
    print(f"  4. fontfactory build {out}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="fontfactory",
        description="Build a font from a glyph sheet.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="slice, vectorize and assemble a sheet")
    p.add_argument("config", help="path to a sheet .toml")
    p.add_argument("--stage", choices=STAGES, help="run a single stage")
    p.add_argument("--through", action="store_true",
                   help="with --stage, run every stage up to and including it")
    p.add_argument("--contact", action="store_true",
                   help="also write a labelled contact sheet")
    p.add_argument("--proof", action="store_true",
                   help="also render specimen text with the built font")
    p.add_argument("--debug", action="store_true",
                   help="keep intermediates and write a grid overlay")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("contact", help="write a labelled contact sheet of the slices")
    p.add_argument("config")
    p.set_defaults(func=cmd_contact)

    p = sub.add_parser("path", help="print the .ttf a config builds")
    p.add_argument("config")
    p.set_defaults(func=cmd_path)

    p = sub.add_parser("proof", help="render specimen text with a built font")
    p.add_argument("font")
    p.add_argument("--text", help="file of lines to render (default: a specimen)")
    p.add_argument("--output", help="output png")
    p.add_argument("--size", type=int, default=56)
    p.set_defaults(func=cmd_proof)

    p = sub.add_parser("render", help="render text with a font")
    p.add_argument("font")
    p.add_argument("--text", help="file of text to render")
    p.add_argument("--string", help="text to render, \\n for line breaks")
    p.add_argument("--output", default="output.png")
    p.add_argument("--size", type=int, default=96)
    p.add_argument("--color", default="black")
    p.add_argument("--bg", help="background colour; omit for transparent")
    p.add_argument("--face", type=int, default=0,
                   help="face index, for a font collection")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("verify", help="inspect a built font's tables")
    p.add_argument("font")
    p.add_argument("--config", help="sheet .toml the font must fully cover")
    p.add_argument("--expect", help="file of characters the font must cover")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("new", help="scaffold a config for a new sheet")
    p.add_argument("config", help="path to write, e.g. sheets/mysheet.toml")
    p.add_argument("--image", help="path to the sheet png")
    p.add_argument("--family", help="font family name")
    p.add_argument("--rows", type=int, default=8)
    p.add_argument("--cols", type=int, default=13)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_new)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
