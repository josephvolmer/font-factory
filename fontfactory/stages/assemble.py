"""Stage 3 — assemble traced outlines into a TTF.

Pure fontTools: no FontForge, no system binaries. That matters because FontForge
hard-links to Homebrew absolute paths (its own Python framework, glib, freetype),
so it cannot be bundled into a distributable .app. Everything here is
pip-installable and relocatable.

Two things decide whether the result reads as a font rather than a pile of
shapes, and neither is inherited from the artwork:

  * *Scale.* Every tile on a sheet is the same size, so a lowercase 'a' arrives
    exactly as tall as a capital 'A'. One scale for both produces small-caps.
    Uppercase keys to cap-height, lowercase to x-height, ascenders in between.

  * *Baseline.* Each glyph is cut as its own tile, so the sheet carries no
    baseline. Every glyph is grounded, then descenders are dropped and hanging
    marks are lifted, by table.
"""

from __future__ import annotations

import json
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.misc.transform import Transform
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

from ..config import Config, char_for

# Max deviation, in em units, when approximating a cubic with quadratics.
CURVE_ERROR = 1.0

# OS/2 ulCodePageRange1, bit 0: "Latin 1" (code page 1252). That page covers the
# ASCII range plus the Latin-1 supplement — the currency and symbol characters a
# ransom-note sheet carries. fontTools computes the *Unicode* range bits for us
# but leaves the code page bits at zero, and zero means "no code pages at all".
CODE_PAGE_LATIN1 = 1 << 0


def _load_outline(path_file: Path) -> RecordingPen:
    """Replay a traced outline (from the vectorize stage) into a pen.

    The geometry arrives already y-up and correctly wound, so nothing is
    reoriented here — see vectorize.trace_glyph for why that is done there.
    """
    pen = RecordingPen()
    for contour in json.loads(path_file.read_text()):
        for seg in contour:
            kind = seg[0]
            if kind == "move":
                pen.moveTo((seg[1], seg[2]))
            elif kind == "line":
                pen.lineTo((seg[1], seg[2]))
            else:
                pen.curveTo(
                    (seg[1], seg[2]), (seg[3], seg[4]), (seg[5], seg[6])
                )
        pen.closePath()
    return pen


def _bounds(pen: RecordingPen):
    """(xmin, ymin, xmax, ymax) of a recorded outline, or None if empty."""
    xs, ys = [], []
    for _, args in pen.value:
        for pt in args:
            if isinstance(pt, tuple):
                xs.append(pt[0])
                ys.append(pt[1])
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def run(cfg: Config, debug: bool = False) -> Path:
    outline_dir = cfg.build_dir / "outlines"
    files = sorted(outline_dir.glob("*.path"))
    if not files:
        raise SystemExit(f"no outlines in {outline_dir} — run the vectorize stage first")

    m = cfg.metrics

    # Pass 1: load every outline and measure it.
    outlines: dict[str, RecordingPen] = {}
    for f in files:
        ch = char_for(f.stem)
        if ch is None:
            print(f"    ! no codepoint for {f.stem!r}, skipping")
            continue
        if ch == " ":
            continue  # space is synthesised, never traced

        pen = _load_outline(f)
        if _bounds(pen) is None:
            print(f"    ! {f.stem!r} traced empty")
            continue
        outlines[ch] = pen

    if not outlines:
        raise SystemExit("no outlines imported")

    def median_height(chars):
        hs = []
        for ch in chars:
            if ch in outlines:
                _, ymin, _, ymax = _bounds(outlines[ch])
                hs.append(ymax - ymin)
        return _median(hs) if hs else None

    # Letters that overshoot (o, s, e are drawn slightly taller than a flat-topped
    # x) and ascenders are excluded from the x-height sample.
    cap_ref = median_height("ABDEFHIJKLMNPRTUVWXYZ") or median_height(outlines)
    x_ref = median_height("acemnruvwxz")
    if cap_ref is None:
        raise SystemExit("could not measure any glyph to derive a scale")

    cap_scale = m.cap_height / cap_ref
    lower_scale = (m.x_height / x_ref) if x_ref else cap_scale
    mid_scale = (cap_scale + lower_scale) / 2

    ascenders = set(m.ascenders)
    descenders = set(m.descenders)

    # Pass 2: scale, ground on the baseline, convert to TrueType glyphs.
    glyphs, widths, cmap = {}, {}, {}
    placed_bounds = []  # every glyph's final box, for the OS/2 clipping metrics

    for ch, pen in sorted(outlines.items()):
        if ch in ascenders:
            scale = mid_scale
        elif ch.isalpha() and ch.islower():
            scale = lower_scale
        else:
            scale = cap_scale

        xmin, ymin, _, _ = _bounds(pen)

        dy = -ymin * scale
        if ch in descenders:
            dy -= m.descender_drop
        elif ch in m.raised:
            dy += m.raised[ch]

        # Scale, sit on the baseline, and start the ink at the side bearing.
        # The matrix is built explicitly because Transform().translate(..).scale(..)
        # composes right-to-left: the translate would be pushed through the scale
        # and its offsets multiplied, which is subtle enough to look like it works.
        transform = Transform(scale, 0, 0, scale,
                              -xmin * scale + m.side_bearing, dy)

        # The tracer emits cubic beziers; TrueType stores quadratics, so the curves
        # are converted on the way in. CURVE_ERROR is in em units — well under a
        # pixel at any real display size.
        tt = TTGlyphPen(None)
        pen.replay(TransformPen(Cu2QuPen(tt, CURVE_ERROR), transform))

        name = f"uni{ord(ch):04X}"
        glyphs[name] = tt.glyph()
        cmap[ord(ch)] = name

        placed = RecordingPen()
        pen.replay(TransformPen(placed, transform))
        box = _bounds(placed)
        placed_bounds.append(box)
        px0, _, px1, _ = box

        # hmtx carries (advance width, left side bearing). The LSB belongs here
        # rather than baked into the outline — TTGlyphPen normalises the contour
        # to the origin, so an offset left in the coordinates is simply dropped.
        widths[name] = (int(round(px1 + m.side_bearing)), int(round(px0)))

    # The space glyph carries no outline, only an advance width.
    space = TTGlyphPen(None).glyph()
    glyphs[".notdef"] = space
    widths[".notdef"] = (m.space_width, 0)
    glyphs["space"] = space
    widths["space"] = (m.space_width, 0)
    cmap[ord(" ")] = "space"

    order = [".notdef", "space"] + [n for n in glyphs if n not in (".notdef", "space")]

    fb = FontBuilder(unitsPerEm=m.em, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(widths)
    fb.setupHorizontalHeader(ascent=m.ascent, descent=-abs(m.descent))
    fb.setupNameTable({
        "familyName": cfg.family,
        "styleName": cfg.style,
        "fullName": f"{cfg.family} {cfg.style}",
        "psName": f"{cfg.family}-{cfg.style}",
        "version": cfg.version,
    })
    # usWinAscent/Descent are a clipping box, not a typographic preference: a
    # renderer may cut off anything outside them. A raised mark can overshoot the
    # nominal ascent (the asterisk on this sheet reaches 801 against an ascent of
    # 800), so the box is measured from the outlines that actually exist rather
    # than assumed from the metrics.
    tops = [b[3] for b in placed_bounds]
    bottoms = [b[1] for b in placed_bounds]
    win_ascent = max(m.ascent, int(max(tops)) if tops else 0)
    win_descent = max(abs(m.descent), int(-min(bottoms)) if bottoms else 0)

    fb.setupOS2(
        sTypoAscender=m.ascent,
        sTypoDescender=-abs(m.descent),
        sTypoLineGap=0,
        usWinAscent=win_ascent,
        usWinDescent=win_descent,
        sCapHeight=m.cap_height,
        sxHeight=m.x_height,
        # Without this the field is left at zero, which reads as "this font
        # supports no code page at all". Renderers that consult it (rather than
        # the cmap) then refuse to use the font for characters it demonstrably
        # has — currency and symbols go missing while the cmap still lists them.
        # Pillow ignores the field entirely, so a preview looks perfect while the
        # installed font drops glyphs: exactly the kind of bug that only shows up
        # once the font leaves the pipeline.
        ulCodePageRange1=CODE_PAGE_LATIN1,
    )
    fb.setupPost()

    out_path = cfg.out_dir / cfg.font_filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(out_path))

    print(f"  assemble   {out_path.name} ({len(cmap)} glyphs, "
          f"cap x{cap_scale:.3f}, lower x{lower_scale:.3f})")
    return out_path
