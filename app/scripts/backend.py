"""JSON-RPC sidecar exposing the fontfactory pipeline to the Electron app.

One request per line on stdin, one response per line on stdout. A long-lived
process rather than one-shot invocations: importing cv2 and fontTools costs a
second or two, and the UI does many small calls (re-slicing on every grid tweak),
so paying that once matters.

    -> {"id": 1, "method": "slice", "params": {...}}
    <- {"id": 1, "ok": true, "result": {...}}
    <- {"id": 1, "ok": false, "error": "..."}

Anything written to stdout that is not a response would corrupt the protocol, so
logging goes to stderr.
"""

from __future__ import annotations

import atexit
import base64
import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

# The pipeline lives one level up from the app.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2
import numpy as np
from PIL import Image

from fontfactory import config as config_mod
from fontfactory import preview
from fontfactory.stages import assemble, slice as slice_stage, vectorize


# Every artefact this app produces lives here and is discarded with the process.
# The app deliberately has no output directory of its own: a built font is a temp
# file until the user saves it somewhere, so nothing is ever written beside their
# artwork or into the source tree.
SESSION = Path(tempfile.mkdtemp(prefix="fontfactory-"))


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def _png_data_url(img) -> str:
    """Encode a PIL image or BGR ndarray as a data: URL for the renderer."""
    if isinstance(img, np.ndarray):
        if img.ndim == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(img)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


_IMAGE_RE = re.compile(r'^(\s*image\s*=\s*)"([^"]*)"', re.M)


def _absolutise_image(toml: str, anchor: Path) -> str:
    """Rewrite `image = "..."` to an absolute path, anchored at `anchor`."""

    def sub(m):
        path = Path(m.group(2))
        if not path.is_absolute():
            path = (anchor / path).resolve()
        return f'{m.group(1)}"{path}"'

    return _IMAGE_RE.sub(sub, toml, count=1)


def _config_from_params(params: dict) -> config_mod.Config:
    """Build a Config from the UI's live state by writing a temp TOML.

    The UI edits a sheet's settings continuously; rather than duplicate the
    validation rules here, the same loader the CLI uses is fed a temp file. That
    keeps one source of truth for what a valid sheet is, including the layout
    row/column check that catches the misaligned grids.

    Everything the app produces — intermediates and the font itself — is written
    under SESSION, never beside the user's artwork and never into the project.
    The app owns no output location: a font exists in temp until the user saves
    it somewhere they chose.
    """
    sheet_path = Path(params["config_path"])
    name = sheet_path.stem

    work = SESSION / name
    work.mkdir(parents=True, exist_ok=True)

    # The loader resolves a relative `image` against the config's own directory,
    # and this config is about to live in temp — so pin the image to an absolute
    # path first. That lets the config sit anywhere without writing so much as a
    # dotfile next to the user's artwork, whose directory may not even be
    # writable.
    toml = _absolutise_image(params["toml"], sheet_path.parent)

    tmp = work / "_config.toml"
    tmp.write_text(toml, encoding="utf-8")

    cfg = config_mod.load(tmp)

    # Override the output locations *after* loading rather than by rewriting the
    # TOML: the config the UI sends already carries an [output] section, and
    # appending a second one is a duplicate-key error. The loaded object is the
    # only place these need to be true.
    cfg.name = name
    cfg.build_dir = work
    cfg.out_dir = work
    return cfg


# --- methods ---------------------------------------------------------------


def m_probe_sheet(params):
    """Open a sheet image and report its size, plus a preview for the UI."""
    img = cv2.imread(params["image"])
    if img is None:
        raise ValueError(f"could not read image: {params['image']}")
    h, w = img.shape[:2]

    scale = min(1.0, 1400 / max(w, h))
    thumb = cv2.resize(img, (int(w * scale), int(h * scale))) if scale < 1 else img

    return {"width": w, "height": h, "preview": _png_data_url(thumb)}


def m_detect_grid(params):
    """Run grid detection and return the cell rectangles, for the overlay."""
    cfg = _config_from_params(params)

    img = cv2.imread(str(cfg.image))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    rows, cols = slice_stage.find_grid(gray, cfg)
    cells = [
        {"row": r, "col": c, "x": x0, "y": y0, "w": x1 - x0 + 1, "h": y1 - y0 + 1}
        for r, (y0, y1) in enumerate(rows)
        for c, (x0, x1) in enumerate(cols)
    ]
    return {"rows": len(rows), "cols": len(cols), "cells": cells}


def m_slice(params):
    """Slice the sheet and return every glyph as a data URL, keyed by character."""
    cfg = _config_from_params(params)
    slice_stage.run(cfg)

    glyphs = []
    for index, ch in enumerate(cfg.layout):
        if ch == " ":
            continue
        png = cfg.build_dir / "glyphs" / f"{config_mod.name_for(ch)}.png"
        glyphs.append({
            "char": ch,
            "name": config_mod.name_for(ch),
            "index": index,
            "row": index // cfg.cols,
            "col": index % cfg.cols,
            "image": _png_data_url(Image.open(png)) if png.exists() else None,
        })

    return {"glyphs": glyphs}


def m_build(params):
    """Run the full pipeline and return the font path.

    No specimen image is rendered here: the app previews the font with live text
    the user types, which subsumes a fixed specimen. `fontfactory proof` still
    exists for the CLI.
    """
    cfg = _config_from_params(params)

    slice_stage.run(cfg)
    vectorize.run(cfg)
    ttf = assemble.run(cfg)

    return {
        "font": str(ttf),
        "coverage": sorted(preview.covered(ttf)),
    }


def m_save_font(params):
    """Copy the built font out of temp to wherever the user chose."""
    src = Path(params["font"])
    dst = Path(params["output"])

    if not src.exists():
        raise ValueError("that font no longer exists — build it again")

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {"output": str(dst)}


def m_render(params):
    """Render arbitrary text with a built font, for the live preview."""
    ttf = Path(params["font"])
    lines = params.get("text", "").split("\n")

    # One reused path rather than a fresh mkdtemp per keystroke, which would leak
    # a directory for every character typed.
    out = SESSION / "preview.png"
    preview.render(
        ttf, out, lines,
        size=int(params.get("size", 96)),
        color=params.get("color", "black"),
        bg=params.get("bg") or None,
    )
    return {"image": _png_data_url(Image.open(out))}


def m_save_render(params):
    """Render to a path the user chose."""
    ttf = Path(params["font"])
    lines = params.get("text", "").split("\n")

    preview.render(
        ttf, Path(params["output"]), lines,
        size=int(params.get("size", 96)),
        color=params.get("color", "black"),
        bg=params.get("bg") or None,
    )
    return {"output": params["output"]}


METHODS = {
    "probe_sheet": m_probe_sheet,
    "detect_grid": m_detect_grid,
    "slice": m_slice,
    "build": m_build,
    "save_font": m_save_font,
    "render": m_render,
    "save_render": m_save_render,
}


def cleanup():
    shutil.rmtree(SESSION, ignore_errors=True)


def main():
    atexit.register(cleanup)
    log(f"fontfactory backend ready (session {SESSION})")
    print(json.dumps({"event": "ready"}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            log("bad request:", line[:200])
            continue

        rid = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        handler = METHODS.get(method)
        if handler is None:
            print(json.dumps(
                {"id": rid, "ok": False, "error": f"unknown method: {method}"}
            ), flush=True)
            continue

        try:
            # The pipeline stages print progress to stdout ("slice 104/104..."),
            # which would land in the middle of the response stream and corrupt
            # the protocol. Send anything they print to stderr instead, where the
            # main process picks it up as log output.
            with contextlib.redirect_stdout(sys.stderr):
                result = handler(params)
            print(json.dumps({"id": rid, "ok": True, "result": result}), flush=True)
        except SystemExit as e:
            # The pipeline raises SystemExit with a human-readable diagnostic
            # (bad grid, layout mismatch). That is a normal failure here, not a
            # crash: surface the message and keep the process alive.
            print(json.dumps({"id": rid, "ok": False, "error": str(e)}), flush=True)
        except Exception as e:
            log(traceback.format_exc())
            print(json.dumps({"id": rid, "ok": False, "error": str(e)}), flush=True)


if __name__ == "__main__":
    main()
