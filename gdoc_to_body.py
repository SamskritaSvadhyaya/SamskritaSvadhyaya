#!/usr/bin/env python3
"""Convert a Google-Drive HTML export (saved tool-result JSON) into a clean,
color-preserving HTML body fragment.

Google's HTML export carries the document's real text colors as inline styles
and embeds images as data URIs. This keeps the colors and bold/italic, extracts
images to <media-dir>/imageN.ext, and drops Google's font/size/alignment cruft.

Usage:
    python3 gdoc_to_body.py <tool-result.json> <media-dir>   # body -> stdout
"""

import base64
import html
import json
import os
import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag

# Colors we drop (let text inherit the default dark ink): pure black, and white
# (which would be invisible on the light reading surface).
DEFAULT_COLORS = {"#000000", "#000", "#ffffff", "#fff"}


def parse_color(style):
    m = re.search(r"color:\s*(#[0-9a-fA-F]{3,6})", style or "")
    return m.group(1).lower() if m else None


def is_bold(style):
    m = re.search(r"font-weight:\s*(\d+)", style or "")
    if m:
        return int(m.group(1)) >= 600
    return "font-weight:bold" in (style or "").replace(" ", "")


def is_italic(style):
    return "font-style:italic" in (style or "").replace(" ", "")


def main():
    json_path, media_dir = sys.argv[1], sys.argv[2]
    data = json.loads(open(json_path, encoding="utf-8").read())
    raw = base64.b64decode(data["content"]).decode("utf-8", "replace")
    soup = BeautifulSoup(raw, "html.parser")
    body = soup.body or soup
    os.makedirs(media_dir, exist_ok=True)
    img_n = [0]

    def handle_img(node):
        src = node.get("src", "")
        m = re.match(r"data:image/([\w.+-]+);base64,(.*)", src, re.S)
        if not m:
            return ""
        ext = m.group(1).lower()
        ext = "jpg" if ext == "jpeg" else ext
        img_n[0] += 1
        fname = f"image{img_n[0]}.{ext}"
        with open(os.path.join(media_dir, fname), "wb") as fh:
            fh.write(base64.b64decode(m.group(2)))
        return f'<img src="media/{fname}" alt="" loading="lazy" />'

    def render(node, inherited):
        if isinstance(node, NavigableString):
            return html.escape(str(node), quote=False)
        if not isinstance(node, Tag):
            return ""
        if node.name == "br":
            return "<br>"
        if node.name == "img":
            return handle_img(node)

        style = node.get("style", "")
        color = parse_color(style) or inherited
        inner = "".join(render(c, color) for c in node.children)
        if not inner:
            return ""

        bold = is_bold(style) or node.name in ("strong", "b")
        ital = is_italic(style) or node.name in ("em", "i")

        if node.name == "a":
            inner = f'<a href="{html.escape(node.get("href", ""), quote=True)}">{inner}</a>'
        if ital:
            inner = f"<em>{inner}</em>"
        if bold:
            inner = f"<strong>{inner}</strong>"
        if color and color not in DEFAULT_COLORS:
            inner = f'<span style="color:{color}">{inner}</span>'
        return inner

    out = []
    for block in body.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "hr"]):
        if block.name == "hr":
            out.append("<hr />")
            continue
        para_color = parse_color(block.get("style", ""))
        content = "".join(render(c, para_color) for c in block.children).strip()
        if not content:
            continue
        tag = block.name
        out.append(f"<{tag}>{content}</{tag}>")

    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
