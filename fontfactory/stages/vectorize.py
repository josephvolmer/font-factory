"""Stage 2 — trace each glyph bitmap into an outline.

Uses `potracer`, a pure-Python port of potrace. The C potrace binary would be
faster, but it is a system dependency, and this pipeline has to bundle into a
distributable app where nothing can be assumed installed. Tracing a hundred small
glyphs is not the bottleneck.

The traced outlines are written to disk as `.path` files — a JSON dump of the
contours — rather than SVG. Going through SVG means serialising to a text format
whose y-axis and winding conventions are the opposite of a font's, then parsing
it back; every round trip is a chance to flip a glyph upside down or turn the
hole in an 'o' into a solid blob. Keeping the geometry in one representation from
tracer to font avoids that entirely.

The slice stage already emits clean ink=black on white, so there is no
thresholding judgement left here. The one decision that matters is the upscale:
sliced glyphs are only ~80px tall, and tracing at that size renders a torn paper
edge as visible polygonal facets. Upscaling first gives the tracer room to lay
down smooth curves, and since the result is a vector it costs nothing downstream.
"""

from __future__ import annotations

import json

import numpy as np
import potrace
from PIL import Image

from ..config import Config


def trace_glyph(img: Image.Image, cfg: Config) -> list[list]:
    """Trace one bitmap into contours, in y-up font orientation.

    Returns a list of contours; each contour is a list of segments:
        ["move", x, y]
        ["line", x, y]
        ["curve", c1x, c1y, c2x, c2y, x, y]

    potracer works in image coordinates (y grows down) and emits every contour
    counter-clockwise. A font wants y up, and TrueType's non-zero fill rule wants
    outer contours and their counters to wind *oppositely* so the holes in 'A' and
    'o' cut rather than fill. Mirroring y already reverses the winding of every
    contour, which is exactly what is needed — so the flip is the whole fix, and
    the point order is left alone.
    """
    t = cfg.trace
    if t.upscale > 1:
        img = img.resize((img.width * t.upscale, img.height * t.upscale), Image.LANCZOS)

    height = img.height

    # potracer traces the *cleared* cells, not the set ones — the inverse of what
    # the name Bitmap(ink) suggests. Passing the ink mask directly traces the
    # background instead, which for a glyph on a white field yields the four
    # corners of the tile as separate contours and turns the letter inside out.
    ink = np.array(img.convert("L")) < 128
    path = potrace.Bitmap(~ink).trace(
        turdsize=t.turdsize,
        alphamax=t.alphamax,
        opttolerance=t.opttolerance,
    )

    def y(v):
        return height - v

    contours = []
    for curve in path:
        segments = [["move", curve.start_point.x, y(curve.start_point.y)]]
        for seg in curve:
            if seg.is_corner:
                segments.append(["line", seg.c.x, y(seg.c.y)])
                segments.append(["line", seg.end_point.x, y(seg.end_point.y)])
            else:
                segments.append([
                    "curve",
                    seg.c1.x, y(seg.c1.y),
                    seg.c2.x, y(seg.c2.y),
                    seg.end_point.x, y(seg.end_point.y),
                ])
        contours.append(segments)

    return contours


def run(cfg: Config, debug: bool = False) -> int:
    src = cfg.build_dir / "glyphs"
    dst = cfg.build_dir / "outlines"

    pngs = sorted(src.glob("*.png"))
    if not pngs:
        raise SystemExit(f"no glyphs in {src} — run the slice stage first")

    dst.mkdir(parents=True, exist_ok=True)
    for stale in dst.glob("*.path"):
        stale.unlink()

    for png in pngs:
        contours = trace_glyph(Image.open(png), cfg)
        (dst / (png.stem + ".path")).write_text(json.dumps(contours))

    print(f"  vectorize  {len(pngs)} outlines")
    return len(pngs)
