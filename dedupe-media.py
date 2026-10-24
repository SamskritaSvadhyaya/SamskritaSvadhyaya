#!/usr/bin/env python3
"""Collapse images repeated across a work's chapters into one shared copy.

Google Docs exports embed the same picture (e.g. a deity image on every
dashaka) into each chapter, so every <work>/<chapter>/media/ ends up with its
own identical copy. This moves each distinct image to <work>/media/<hash>.<ext>,
rewrites the chapter pages to point at it, updates the chapter "image" fields in
texts.json, and re-encodes oversized PNG photos as JPEG.

Usage:
    python3 dedupe-media.py <work-dir>      # e.g. narayaneeyam
"""

import hashlib
import io
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "texts.json"
MAX_WIDTH = 900          # px; the reading column never shows images wider than this
PNG_TO_JPEG_BYTES = 300_000  # re-encode PNGs larger than this as JPEG


def shrink(data, ext):
    """Return (bytes, ext), downscaled/re-encoded if the image is oversized."""
    if ext != "png" or len(data) < PNG_TO_JPEG_BYTES:
        return data, ext
    im = Image.open(io.BytesIO(data))
    if im.mode in ("RGBA", "LA", "P"):
        return data, ext  # keep transparency as-is
    if im.width > MAX_WIDTH:
        im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)), Image.LANCZOS)
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=85, optimize=True, progressive=True)
    return out.getvalue(), "jpg"


def main():
    work = sys.argv[1].strip("/")
    work_dir = ROOT / work
    shared = work_dir / "media"
    shared.mkdir(exist_ok=True)
    renamed = {}  # (chapter, filename) -> shared filename

    for media in sorted(work_dir.glob("*/media")):
        chapter = media.parent.name
        for f in sorted(media.iterdir()):
            data = f.read_bytes()
            key = hashlib.sha1(data).hexdigest()[:12]
            existing = next(shared.glob(f"{key}.*"), None)
            if existing is None:
                small, ext = shrink(data, f.suffix.lstrip(".").lower())
                existing = shared / f"{key}.{ext}"
                existing.write_bytes(small)
            renamed[(chapter, f.name)] = existing.name
        shutil.rmtree(media)

    for (chapter, old), new in renamed.items():
        page = work_dir / chapter / "index.html"
        html = page.read_text(encoding="utf-8")
        html = re.sub(rf'src="(?:\./)?media/{re.escape(old)}"', f'src="../media/{new}"', html)
        page.write_text(html, encoding="utf-8")

    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for e in entries:
        if e.get("slug") != work:
            continue
        for c in e.get("chapters", []):
            img = c.get("image") or ""
            m = re.fullmatch(rf"{re.escape(work)}/([^/]+)/media/(.+)", img)
            if m and (m.group(1), m.group(2)) in renamed:
                c["image"] = f"{work}/media/{renamed[(m.group(1), m.group(2))]}"
    MANIFEST.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    n = len({v for v in renamed.values()})
    size = sum(p.stat().st_size for p in shared.iterdir())
    print(f"{work}: {len(renamed)} chapter image(s) -> {n} shared file(s), {size // 1024} KB")


if __name__ == "__main__":
    main()
