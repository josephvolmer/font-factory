"""Stage 1 — cut the sheet into one clean bitmap per character.

Two problems have to be solved per tile, and they are independent:

  1. *Where is the tile?* Hand-made sheets do not sit on an exact lattice, so the
     grid is found by projecting the non-background mask rather than by dividing
     the image into equal cells. A config can override this with fixed bounds.

  2. *Which pixels are the letter?* On a ransom-note sheet the polarity flips from
     tile to tile (white-on-red beside black-on-cream), so ink is decided per
     tile. And because neighbouring tiles bleed a strip into every crop, the
     letter is picked out structurally: it is the largest component that does not
     touch the crop border.

Output is normalised to ink=black on white, which is what the tracer expects.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..config import Config, name_for


def _bands(signal, min_run: int, thresh: float):
    """Contiguous runs where `signal` exceeds `thresh`, at least `min_run` long."""
    on = signal > thresh
    out, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_run:
                out.append((start, i - 1))
            start = None
    if start is not None and len(on) - start >= min_run:
        out.append((start, len(on) - 1))
    return out


def tile_mask(gray, cfg: Config):
    """Boolean mask that is True on the tiles and False on the gaps between them.

    Segmentation works by finding the gutters, so it has to know which luminance
    is background. Sheets differ: a ransom-note sheet is bright tiles on black,
    a scanned sheet is often cream tiles on white. Guessing wrong merges the whole
    image into one blob.

    The border of the image is background by construction, so "auto" reads it
    there rather than assuming.
    """
    g = cfg.grid

    threshold = g.bg_threshold
    if threshold <= 0:
        threshold, _ = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

    background = g.background
    if background == "auto":
        border = np.concatenate([
            gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1],
        ])
        background = "dark" if np.median(border) < threshold else "light"

    if background == "dark":
        return gray > threshold      # tiles are the bright regions
    return gray < threshold          # tiles are the dark regions


def find_grid(gray, cfg: Config):
    """Return (row_bounds, col_bounds), each a list of (start, end) pixel pairs."""
    g = cfg.grid
    h, w = gray.shape

    if g.mode == "fixed":
        cell_w = (g.right - g.left) / cfg.cols
        cell_h = (g.bottom - g.top) / cfg.rows
        rows = [(int(g.top + r * cell_h), int(g.top + (r + 1) * cell_h) - 1)
                for r in range(cfg.rows)]
        cols = [(int(g.left + c * cell_w), int(g.left + (c + 1) * cell_w) - 1)
                for c in range(cfg.cols)]
        return rows, cols

    mask = tile_mask(gray, cfg).astype(np.uint8)
    if g.ignore_top:
        mask[:g.ignore_top, :] = 0

    rows = _bands(mask.sum(1), min_run=30, thresh=w * 0.02)
    cols = _bands(mask.sum(0), min_run=30, thresh=h * 0.02)

    if len(rows) != cfg.rows or len(cols) != cfg.cols:
        raise SystemExit(
            f"grid detection found {len(rows)} rows x {len(cols)} cols, "
            f"but the config declares {cfg.rows} x {cfg.cols}.\n"
            f"  Try: sheet.grid.background = 'dark' or 'light' "
            f"(tiles brighter or darker than the gaps between them),\n"
            f"       sheet.grid.ignore_top to skip a title bar,\n"
            f"       sheet.grid.bg_threshold to set the cutoff by hand,\n"
            f"       or sheet.grid.mode = 'fixed' with explicit pixel bounds.\n"
            f"  Run with --debug to write build/{cfg.name}/grid_overlay.png "
            f"and see what it found."
        )
    return rows, cols


def extract_ink(tile_bgr, cfg: Config):
    """Ink-as-black-on-white for one tile, whatever its colour scheme."""
    gray = cv2.cvtColor(tile_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    polarity = cfg.ink.polarity
    if polarity == "auto":
        # Brightness alone cannot say which cluster is the ink, since both
        # white-on-black and black-on-white occur. Area can: a letter always
        # covers less of its tile than the background does.
        dark_is_ink = (binary == 255).sum() > (binary == 0).sum()
    else:
        dark_is_ink = polarity == "dark_on_light"

    ink = (binary == 0) if dark_is_ink else (binary == 255)

    out = np.full(gray.shape, 255, np.uint8)
    out[ink] = 0
    return out


def isolate_letter(img, cfg: Config):
    """Keep the letter, discard strips bleeding in from neighbouring tiles.

    The separating property is structural, not a size threshold: the letter is
    centred on its own tile and clears the crop border, while every leaked
    fragment touches it. Thresholding on area or thinness misclassifies large
    debris (a neighbour's stroke can be 20% of the ink and most of the width).
    """
    ink = (img < 128).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    if n <= 1:
        return img

    h, w = img.shape
    min_blob = cfg.ink.min_blob

    def touches_edge(i):
        x, y, bw, bh, _ = stats[i]
        return x == 0 or y == 0 or x + bw == w or y + bh == h

    # Paper grain is never part of a glyph, so specks are not candidates for
    # anything: not the letter, not a mark to re-attach.
    blobs = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_blob]
    if not blobs:
        return img

    interior = [i for i in blobs if not touches_edge(i)]
    if interior:
        best = max(interior, key=lambda i: stats[i, cv2.CC_STAT_AREA])
    else:
        # The letter genuinely runs to the tile edge (M and m often do).
        best = max(blobs, key=lambda i: stats[i, cv2.CC_STAT_AREA])

    letter = labels == best

    # Re-attach interior marks that are separate components but belong to the
    # glyph: the dot on i/j, both dots of a colon, the bar of a %.
    x, _, bw, _, _ = stats[best]
    for i in interior:
        if i == best:
            continue
        ix, _, ibw, _, _ = stats[i]
        if ix + ibw > x - 4 and ix < x + bw + 4:  # shares the letter's column
            letter |= labels == i

    out = np.full(img.shape, 255, np.uint8)
    out[letter] = 0
    return out


def trim(img):
    """Crop tight to the ink. None if the tile is blank."""
    ys, xs = np.where(img < 128)
    if len(xs) == 0:
        return None
    return img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def run(cfg: Config, debug: bool = False) -> int:
    img = cv2.imread(str(cfg.image))
    if img is None:
        raise SystemExit(f"could not read sheet image: {cfg.image}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cfg.build_dir.mkdir(parents=True, exist_ok=True)

    if debug:
        # Write the mask before detection can fail: when the grid is wrong this
        # picture is the whole diagnosis, so it is worthless if it only appears
        # on success.
        mask = tile_mask(gray, cfg).astype(np.uint8) * 255
        cv2.imwrite(str(cfg.build_dir / "tile_mask.png"), mask)

    rows, cols = find_grid(gray, cfg)

    if debug:
        overlay = img.copy()
        for y0, y1 in rows:
            for x0, x1 in cols:
                cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 255, 0), 2)
        cv2.imwrite(str(cfg.build_dir / "grid_overlay.png"), overlay)

    out_dir = cfg.build_dir / "glyphs"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.png"):
        stale.unlink()

    pad = cfg.grid.pad
    written, skipped = 0, []
    for r, (y0, y1) in enumerate(rows):
        for c, (x0, x1) in enumerate(cols):
            ch = cfg.cell_char(r * cfg.cols + c)
            if ch is None or ch == " ":
                continue  # a space in the layout marks an intentionally empty cell

            tile = img[y0 + pad:y1 - pad + 1, x0 + pad:x1 - pad + 1]
            mask = extract_ink(tile, cfg)
            if cfg.ink.isolate:
                mask = isolate_letter(mask, cfg)

            glyph = trim(mask)
            if glyph is None:
                skipped.append((ch, r, c))
                continue

            cv2.imwrite(str(out_dir / f"{name_for(ch)}.png"), glyph)
            written += 1

    for ch, r, c in skipped:
        print(f"    ! no ink found for {ch!r} at row {r + 1}, col {c + 1}")

    expected = sum(1 for ch in cfg.layout if ch != " ")
    print(f"  slice      {written}/{expected} glyphs")
    return written
