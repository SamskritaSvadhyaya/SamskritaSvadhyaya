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

# Pictures in the docs are not shown on the site.
KEEP_IMAGES = False

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


def align(style):
    m = re.search(r"text-align:\s*(left|right|center|justify)", style or "")
    a = m.group(1) if m else None
    # left is the default; only carry non-default alignment to match the source
    return a if a in ("center", "right", "justify") else None


# The document's body text is 11pt; express sizes relative to it so the doc's
# size hierarchy is reproduced while still scaling with the reader's A+/A- control.
BASE_PT = 11.0


def font_size_em(style):
    m = re.search(r"font-size:\s*([\d.]+)pt", style or "")
    if not m:
        return None
    em = round(float(m.group(1)) / BASE_PT, 2)
    return em if em != 1.0 else None


# The opening dhyana shlokas are typed as two separate paragraphs in the docs, which
# the site spaces apart. Join each one's two halves into one centred couplet (line
# break, no paragraph gap), like the other prayer verses. Pairs: (first half, second half).
_DHYANA_PAIRS = [
    ("मनोजवं", "वातात्मजं"),            # Story of Hanuman
    ("असाध्यसाधकस्वामिन्", "रामदूत कृपासिन्धो"),  # Story of Hanuman (second invocation)
    ("वसुदेवसुतं", "देवकीपरमानन्दं"),    # Narayaneeyam
    ("काले वर्षतु", "देशोऽयं"),          # Kavyakusumanjali (Eclectic Collection)
    ("रामाय रामभद्राय", "रघुनाथाय नाथाय"),  # Raghuvamsha / Kishkindhakanda invocation
    ("जय श्री हनुमान्", "सर्वं श्री कृष्णार्पणमस्तु"),  # Story of Hanuman note: closing lines
]
_DHYANA = [
    re.compile(
        rf'(<p[^>]*>)((?:(?!</p>).)*{a}(?:(?!</p>).)*)</p>\s*'
        rf'<p[^>]*>((?:(?!</p>).)*{b}(?:(?!</p>).)*)</p>',
        re.S,
    )
    for a, b in _DHYANA_PAIRS
]


def join_dhyana(html_text):
    for pat in _DHYANA:
        html_text = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}<br>{m.group(3)}</p>", html_text)
    return join_verses(html_text)


# Every shloka is typed one line per paragraph in the docs, which the site spaces a
# paragraph apart. Join each shloka's lines into one centred block (line breaks, no
# gaps). A shloka line is a centred paragraph of coloured Devanagari (verses are green,
# invocations blue; headings are uncoloured and never joined) that doesn't start with
# "(" (metre / shloka-count notes). Consecutive lines with the same styling form a run;
# the run is split into shlokas after each line ending in ॥. If the run's last line does
# not end in ॥ (the doc groups part-verses together above one meaning, e.g. 3-line
# Ramayana verses), the whole run is one block. Safe to re-run on its own output.
_CENTRED_P = re.compile(r'<p style="text-align:center">(.*)</p>')
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _verse_line(inner):
    text = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
    if not _DEVANAGARI.search(text) or text.startswith("("):
        return None
    # Coloured styling of the Devanagari text itself (ignores spans holding only spaces,
    # and stray uncoloured words inside an otherwise coloured line).
    styles = tuple(sorted({
        style for style, body in re.findall(r'<span style="([^"]*)">(.*?)</span>', inner, re.S)
        if _DEVANAGARI.search(body) and "color:" in style
    }))
    if not styles:
        return None
    return styles, text.endswith("॥")


def join_verses(html_text):
    nl = "\r\n" if "\r\n" in html_text else "\n"
    out, run = [], []  # run: [(original line, inner html, styles, ends_with_double_danda)]

    def emit(seg):
        if len(seg) > 1:
            out.append('<p style="text-align:center">' + "<br>".join(r[1] for r in seg) + "</p>")
        else:
            out.extend(r[0] for r in seg)

    def flush():
        segs, cur = [], []
        for r in run:
            cur.append(r)
            if r[3]:
                segs.append(cur)
                cur = []
        if cur:  # run doesn't end in ॥: the doc groups it all above one meaning
            segs = [list(run)]
        for seg in segs:
            emit(seg)
        run.clear()

    for line in html_text.split(nl):
        m = _CENTRED_P.fullmatch(line)
        info = _verse_line(m.group(1)) if m else None
        if info is None:
            flush()
            out.append(line)
            continue
        styles, ends = info
        if run and styles != run[-1][2]:
            flush()
        run.append((line, m.group(1), styles, ends))
    flush()
    return nl.join(out)


_MEANING_LABEL = re.compile(
    r"\s*(Word[\s-]*by[\s-]*word meaning|Anvaya?|Literal meaning|Simple meaning)\b", re.I)


def main():
    json_path, media_dir = sys.argv[1], sys.argv[2]
    data = json.loads(open(json_path, encoding="utf-8").read())
    raw = base64.b64decode(data["content"]).decode("utf-8", "replace")
    soup = BeautifulSoup(raw, "html.parser")
    body = soup.body or soup
    img_n = [0]

    def handle_img(node):
        # The site shows no pictures (owner's decision, 2026-11-09): every picture in a doc
        # is left out. A paragraph holding only a picture then becomes empty and is skipped.
        if not KEEP_IMAGES:
            return ""
        os.makedirs(media_dir, exist_ok=True)
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
        props = []
        if color and color not in DEFAULT_COLORS:
            props.append(f"color:{color}")
        size = font_size_em(style)
        if size:
            props.append(f"font-size:{size}em")
        if props:
            inner = f'<span style="{";".join(props)}">{inner}</span>'
        return inner

    out = []
    for block in body.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "hr"]):
        # Google puts the doc's page header and footer in <div>s directly under <body>
        # (the text itself is not in a div). They stay in the doc but are left off the site.
        if any(par.name == "div" and par.parent is body for par in block.parents):
            continue
        if block.name == "hr":
            out.append("<hr />")
            continue
        bstyle = block.get("style", "")
        para_color = parse_color(bstyle)
        content = "".join(render(c, para_color) for c in block.children).strip()
        if not content:
            continue
        # Drop Google Docs' auto-injected tab labels ("Tab 1", "Tab 2.3", ...).
        plain = block.get_text(strip=True)
        if re.fullmatch(r"Tab \d+(\.\d+)*", plain):
            continue
        # A picture inside a line of text (e.g. a number pasted as an image) is part of
        # the sentence: mark it inline so it renders at text size, not as an illustration.
        if "<img" in content and plain:
            content = content.replace("<img ", '<img class="inline" ')
        tag = block.name
        # A meaning paragraph accidentally given a Heading style in the doc ("Anvaya: …"
        # as Heading 2) is still body text: render it as a normal paragraph.
        mislabelled = tag != "p" and bool(_MEANING_LABEL.match(plain))
        if mislabelled:
            tag = "p"
        props = []
        a = align(bstyle)
        if a:
            props.append(f"text-align:{a}")
        size = font_size_em(bstyle)
        if size and not mislabelled:
            props.append(f"font-size:{size}em")
        attr = f' style="{";".join(props)}"' if props else ""
        out.append(f"<{tag}{attr}>{content}</{tag}>")

    # Plain English spelling (Raghuvamsha, not Raghuvaṃśa) — the owner's style.
    from plain_english import plain
    sys.stdout.write(plain(join_dhyana("\n".join(out))) + "\n")


if __name__ == "__main__":
    main()
