"""Visual checks — the fastest way to catch a misconfigured sheet.

A contact sheet renders each sliced glyph *under the character it was filed as*.
A grid that is off by one cell produces a font that builds cleanly, reports the
right glyph count, and is entirely wrong; the only cheap way to see that is to
look at it. Build one before trusting a new sheet.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

from .config import Config, name_for

_LABEL_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _label_font(size: int):
    for path in _LABEL_FONTS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


def contact_sheet(cfg: Config, out_path: Path | None = None) -> Path:
    """Render every sliced glyph beneath the name it was saved as."""
    glyph_dir = cfg.build_dir / "glyphs"
    out_path = out_path or (cfg.build_dir / "contact_sheet.png")

    cell_w, cell_h, label_h = 110, 120, 20
    font = _label_font(13)

    width = cell_w * cfg.cols
    height = (cell_h + label_h) * cfg.rows
    sheet = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)

    for index, ch in enumerate(cfg.layout):
        r, c = divmod(index, cfg.cols)
        x0, y0 = c * cell_w, r * (cell_h + label_h)

        draw.rectangle(
            [x0, y0, x0 + cell_w, y0 + cell_h + label_h], outline=(205, 205, 205)
        )

        if ch == " ":
            draw.rectangle(
                [x0 + 1, y0 + 1, x0 + cell_w - 1, y0 + cell_h - 1],
                fill=(246, 246, 246),
            )
            continue

        stem = name_for(ch)
        png = glyph_dir / f"{stem}.png"

        if png.exists():
            img = Image.open(png).convert("L")
            img.thumbnail((cell_w - 16, cell_h - 16))
            sheet.paste(img, (x0 + (cell_w - img.width) // 2,
                              y0 + (cell_h - img.height) // 2))
        else:
            draw.text((x0 + 10, y0 + cell_h // 2 - 6), "MISSING",
                      fill=(200, 0, 0), font=font)

        draw.rectangle(
            [x0, y0 + cell_h, x0 + cell_w, y0 + cell_h + label_h],
            fill=(234, 234, 246),
        )
        draw.text((x0 + 5, y0 + cell_h + 3), stem, fill=(0, 0, 150), font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return out_path


DEFAULT_PROOF = [
    "Ransom Note",
    "ABCDEFGHIJKLM NOPQRSTUVWXYZ",
    "abcdefghijklm nopqrstuvwxyz",
    "0123456789",
    "typing jumpy quags",
    '"Pay up," he said; (why?)',
]


def covered(ttf: Path) -> set[str]:
    """Every character the font has a glyph for."""
    from fontTools.ttLib import TTFont

    return {chr(cp) for cp in TTFont(str(ttf)).getBestCmap()}


def _color(spec: str | None, default=None):
    """Parse a colour name/hex, or 'transparent'/None for a clear background."""
    if spec is None:
        return default
    if spec.lower() in ("none", "transparent"):
        return (0, 0, 0, 0)
    rgb = ImageColor.getrgb(spec)
    return rgb if len(rgb) == 4 else (*rgb, 255)


def render(
    ttf: Path,
    out_path: Path,
    lines: list[str],
    size: int = 56,
    color: str = "black",
    bg: str | None = None,
    face_index: int = 0,
    pad: int = 40,
    gap: int = 14,
) -> Path:
    """Render lines of text with a font. `bg=None` gives a transparent image."""
    font = ImageFont.truetype(str(ttf), size, index=face_index)
    lines = lines or [""]

    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    width = height = 0
    for line in lines:
        left, top, right, bottom = measure.textbbox((0, 0), line, font=font)
        width = max(width, right - left)
        height += (bottom - top) + gap
    height = max(0, height - gap)

    img = Image.new(
        "RGBA",
        (width + pad * 2, height + pad * 2),
        _color(bg, (0, 0, 0, 0)),
    )
    draw = ImageDraw.Draw(img)

    y = pad
    for line in lines:
        left, top, right, bottom = measure.textbbox((0, 0), line, font=font)
        # Offset by the bbox origin so the first glyph starts flush at the pad,
        # rather than inset by whatever bearing the font happens to have.
        draw.text((pad - left, y - top), line, font=font, fill=_color(color))
        y += (bottom - top) + gap

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


def proof(ttf: Path, out_path: Path, lines: list[str] | None = None,
          size: int = 56) -> Path:
    """Render a specimen, filtered to what the font actually covers.

    A sheet with no lowercase should proof as the font it is, not as a wall of
    .notdef boxes that reads like a build failure.
    """
    if lines is None:
        have = covered(ttf)
        lines = []
        for line in DEFAULT_PROOF:
            kept = "".join(c for c in line if c == " " or c in have)
            if kept.strip():
                lines.append(kept)
        if not lines:
            lines = ["".join(sorted(c for c in have if c.isprintable() and c != " "))]

    return render(ttf, out_path, lines, size=size, color="black", bg="white")
