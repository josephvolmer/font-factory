"""Load and validate a sheet config.

A sheet config is the complete description of one glyph sheet: where the image
is, how its characters are laid out, and how the resulting font should be
proportioned. Everything sheet-specific lives here so that no stage needs
editing to support a new sheet.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


# Filesystem-safe stems for characters that cannot be filenames. Shared by the
# slice stage (writing PNGs) and the assemble stage (mapping them back to
# codepoints), so the two can never drift apart.
CHAR_NAMES = {
    ".": "period", ",": "comma", "!": "exclam", "?": "question",
    ":": "colon", ";": "semicolon", "'": "apostrophe", '"': "quote",
    "(": "lparen", ")": "rparen", "{": "lbrace", "}": "rbrace",
    "[": "lbracket", "]": "rbracket", "/": "slash", "\\": "backslash",
    "|": "bar", "+": "plus", "-": "minus", "_": "underscore",
    "=": "equals", "<": "lt", ">": "gt", "@": "at", "#": "hash",
    "$": "dollar", "%": "percent", "^": "caret", "&": "amp",
    "*": "asterisk", "~": "tilde", "`": "grave", " ": "space",
    "€": "euro", "£": "sterling", "¥": "yen", "¢": "cent",
    "©": "copyright", "®": "registered", "™": "trademark",
    "÷": "divide", "±": "plusminus", "×": "multiply", "§": "section",
    "¶": "paragraph", "†": "dagger", "‡": "doubledagger", "•": "bullet",
    "…": "ellipsis", "–": "endash", "—": "emdash", "°": "degree",
}


def name_for(ch: str) -> str:
    """Filesystem-safe stem for a character."""
    if ch in CHAR_NAMES:
        return CHAR_NAMES[ch]
    if ch.isalpha() and ch.islower():
        # Uppercase and lowercase collide on case-insensitive filesystems (macOS).
        return ch + "_lower"
    return ch


def char_for(stem: str) -> str | None:
    """Inverse of name_for. Returns None if the stem is not a known character."""
    if stem.endswith("_lower") and len(stem) == len("x_lower"):
        return stem[0]
    for ch, name in CHAR_NAMES.items():
        if name == stem:
            return ch
    if len(stem) == 1:
        return stem
    return None


@dataclass
class Grid:
    """How to find the glyph tiles on the sheet."""

    mode: str = "auto"          # "auto" (projection) or "fixed" (explicit bounds)
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0
    ignore_top: int = 0         # rows of the image to ignore (title bars, etc.)
    pad: int = 3                # shave the tile edge before segmenting

    # Which side of `bg_threshold` the *background* falls on. A ransom-note sheet
    # is bright tiles on black ("dark"); a scan is often cream tiles on white
    # ("light"). Detection needs to know, because it segments by finding the gaps
    # between tiles. "auto" infers it from the image border, which is background
    # by construction.
    background: str = "auto"    # "auto" | "dark" | "light"
    bg_threshold: int = 0       # 0 means "pick one automatically" (Otsu)


@dataclass
class Ink:
    """How to separate the letter from its tile."""

    # "auto" decides per tile via Otsu + minority-area, which handles sheets whose
    # polarity flips (white-on-red next to black-on-cream). Force it when a sheet
    # is uniform and auto guesses wrong on sparse glyphs like the period.
    polarity: str = "auto"      # "auto" | "dark_on_light" | "light_on_dark"
    min_blob: int = 12          # ignore specks smaller than this (paper grain)
    isolate: bool = True        # keep only the letter, drop bleed-in from neighbours


@dataclass
class Trace:
    """potrace settings."""

    upscale: int = 4
    alphamax: float = 1.0
    opttolerance: float = 0.2
    turdsize: int = 8


@dataclass
class Metrics:
    """Font proportions, in em units."""

    em: int = 1000
    cap_height: int = 700
    x_height: int = 500
    ascent: int = 800
    descent: int = 200
    side_bearing: int = 40
    space_width: int = 260
    descender_drop: int = 150

    descenders: str = "gjpqy,;"
    ascenders: str = "bdfhklt"
    # Marks that hang from above rather than resting on the baseline,
    # as character -> how far to lift it, in em units.
    raised: dict = field(default_factory=lambda: {
        "'": 380, '"': 380, "`": 380, "^": 300, "*": 300, "™": 300,
        "~": 180, "-": 200, "=": 120, "+": 120, "÷": 120, "×": 120,
        "<": 100, ">": 100, "±": 100, "°": 380,
    })


@dataclass
class Config:
    path: Path
    name: str                   # config stem, used for build dir naming
    family: str
    style: str
    version: str
    image: Path
    rows: int
    cols: int
    layout: str                 # characters in reading order, no newlines
    grid: Grid
    ink: Ink
    trace: Trace
    metrics: Metrics
    out_dir: Path
    build_dir: Path

    @property
    def font_filename(self) -> str:
        return f"{self.family}-{self.style}.ttf"

    def cell_char(self, index: int) -> str | None:
        """The character at a given cell, in reading order."""
        return self.layout[index] if index < len(self.layout) else None


def _require(table: dict, key: str, where: str):
    if key not in table:
        raise SystemExit(f"config: [{where}] is missing required key '{key}'")
    return table[key]


def load(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"config not found: {path}")

    with path.open("rb") as f:
        raw = tomllib.load(f)

    root = path.parent

    font = raw.get("font", {})
    sheet = raw.get("sheet", {})

    family = _require(font, "family", "font")
    style = font.get("style", "Regular")

    image = Path(_require(sheet, "image", "sheet"))
    if not image.is_absolute():
        image = (root / image).resolve()
    if not image.exists():
        raise SystemExit(f"sheet image not found: {image}")

    rows = int(_require(sheet, "rows", "sheet"))
    cols = int(_require(sheet, "cols", "sheet"))

    # The layout is written as a visual block so it mirrors the sheet: one line
    # per row of tiles. Blank lines and trailing whitespace are ignored, but
    # interior spaces are significant (a space means "this cell is empty").
    layout_raw = _require(sheet, "layout", "sheet")
    lines = [ln for ln in layout_raw.splitlines() if ln.strip()]
    layout = "".join(lines)

    if len(lines) != rows:
        raise SystemExit(
            f"config: layout has {len(lines)} rows but sheet.rows = {rows}.\n"
            f"  Each line of `layout` must correspond to one row of tiles."
        )
    for i, ln in enumerate(lines):
        if len(ln) != cols:
            raise SystemExit(
                f"config: layout row {i + 1} has {len(ln)} characters "
                f"but sheet.cols = {cols}.\n"
                f"    {ln!r}\n"
                f"  Pad short rows with spaces to mark empty cells."
            )

    g = sheet.get("grid", {})
    grid = Grid(
        mode=g.get("mode", "auto"),
        left=int(g.get("left", 0)),
        top=int(g.get("top", 0)),
        right=int(g.get("right", 0)),
        bottom=int(g.get("bottom", 0)),
        ignore_top=int(g.get("ignore_top", 0)),
        pad=int(g.get("pad", 3)),
        background=g.get("background", "auto"),
        bg_threshold=int(g.get("bg_threshold", 0)),
    )
    if grid.mode not in ("auto", "fixed"):
        raise SystemExit(f"config: sheet.grid.mode must be 'auto' or 'fixed', got {grid.mode!r}")
    if grid.background not in ("auto", "dark", "light"):
        raise SystemExit(
            f"config: sheet.grid.background must be 'auto', 'dark' or 'light', "
            f"got {grid.background!r}"
        )
    if grid.mode == "fixed" and not (grid.right and grid.bottom):
        raise SystemExit("config: sheet.grid.mode = 'fixed' requires left/top/right/bottom")

    i = raw.get("ink", {})
    ink = Ink(
        polarity=i.get("polarity", "auto"),
        min_blob=int(i.get("min_blob", 12)),
        isolate=bool(i.get("isolate", True)),
    )
    if ink.polarity not in ("auto", "dark_on_light", "light_on_dark"):
        raise SystemExit(f"config: ink.polarity invalid: {ink.polarity!r}")

    t = raw.get("trace", {})
    trace = Trace(
        upscale=int(t.get("upscale", 4)),
        alphamax=float(t.get("alphamax", 1.0)),
        opttolerance=float(t.get("opttolerance", 0.2)),
        turdsize=int(t.get("turdsize", 8)),
    )

    m = raw.get("metrics", {})
    defaults = Metrics()
    metrics = Metrics(
        em=int(m.get("em", defaults.em)),
        cap_height=int(m.get("cap_height", defaults.cap_height)),
        x_height=int(m.get("x_height", defaults.x_height)),
        ascent=int(m.get("ascent", defaults.ascent)),
        descent=int(m.get("descent", defaults.descent)),
        side_bearing=int(m.get("side_bearing", defaults.side_bearing)),
        space_width=int(m.get("space_width", defaults.space_width)),
        descender_drop=int(m.get("descender_drop", defaults.descender_drop)),
        descenders=m.get("descenders", defaults.descenders),
        ascenders=m.get("ascenders", defaults.ascenders),
        raised={**defaults.raised, **m.get("raised", {})},
    )

    # Output paths anchor to the working directory, not to the config's folder:
    # `dir = "fonts"` should mean the project's fonts/, however deep in sheets/
    # the config happens to sit. (The sheet *image* is the opposite — it is
    # resolved against the config, since it belongs to the config.)
    out = raw.get("output", {})
    out_dir = Path(out.get("dir", "fonts")).expanduser()
    if not out_dir.is_absolute():
        out_dir = (Path.cwd() / out_dir).resolve()

    build_dir = Path(out.get("build_dir", "build")).expanduser()
    if not build_dir.is_absolute():
        build_dir = (Path.cwd() / build_dir).resolve()
    build_dir = build_dir / path.stem

    return Config(
        path=path,
        name=path.stem,
        family=family,
        style=style,
        version=str(font.get("version", "1.0")),
        image=image,
        rows=rows,
        cols=cols,
        layout=layout,
        grid=grid,
        ink=ink,
        trace=trace,
        metrics=metrics,
        out_dir=out_dir,
        build_dir=build_dir,
    )
