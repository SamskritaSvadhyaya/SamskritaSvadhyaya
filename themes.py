#!/usr/bin/env python3
"""Bhagavad Geeta themes: shlokas on one idea, gathered across chapters.

Source: the owner's Google Doc "Geeta Themes" (Drive folder "Bhagavad Geeta"). Each theme is a
heading (or a bold line), then optionally a few lines of introduction, then the shloka numbers:

    Desireless action
    (optional introduction)
    2.47, 2.48, 3.19, 4.20, 18.6

  python themes.py import <download.json>   # doc (HTML export) -> geeta-themes.json, then build
  python themes.py build                    # pages only (also run by `build.py home`)

Pages (public): bhagavad-geeta/themes/ (all themes) and bhagavad-geeta/themes/<slug>/ - every
shloka in full with its simple meaning, read from the chapter pages, linked to its chapter.
Shlokas from chapters not on the site yet are left out until the chapter is published.
Each chapter page gets <script id="shloka-themes"> (which of its shlokas are in which themes);
script.js shows "Theme: …" under those shlokas.
"""
import base64
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "geeta-themes.json"
WORK = ROOT / "bhagavad-geeta"
OUT = WORK / "themes"
SITE = "https://samskritasvadhyaya.github.io/SamskritaSvadhyaya/"
REF = re.compile(r"(\d{1,2})\s*\.\s*(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "theme"


# ---------------------------------------------------------------- doc -> geeta-themes.json
def parse_doc(download):
    from bs4 import BeautifulSoup
    from plain_english import plain
    doc = json.loads(Path(download).read_text(encoding="utf-8"))
    raw = base64.b64decode(doc["content"]).decode("utf-8")
    soup = BeautifulSoup(raw, "html.parser")
    body = soup.body or soup
    for div in body.find_all("div", recursive=False):      # Google's page header / footer
        div.decompose()
    blocks = body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"])
    use_headings = any(b.name not in ("p", "li") and b.get_text(strip=True) for b in blocks)

    def is_refs(text):
        rest = REF.sub("", text)
        return REF.search(text) and not re.sub(r"[\s,;.&]|and", "", rest, flags=re.I)

    def is_bold_line(b):
        t = b.get_text(" ", strip=True)
        if not t or len(t) > 90:
            return False
        spans = [s for s in b.find_all("span") if s.get_text(strip=True)]
        return spans and all(re.search(r"font-weight\s*:\s*(700|bold)", s.get("style", "")) for s in spans)

    themes, cur = [], None
    shlokas_label = re.compile(r"^\s*shlokas?\s*[:\-–]\s*(.*)$", re.I)

    def drop_empty_label():
        # "This teaches:" with nothing written after it yet
        if cur and cur["intro"] and cur["intro"][-1].rstrip().endswith(":"):
            cur["intro"].pop()

    for b in blocks:
        text = re.sub(r"\s+", " ", b.get_text(" ", strip=True)).strip()
        if not text:
            continue
        label = shlokas_label.match(text)                      # "Shlokas: 9.4, 9.16 …"
        refs_only = cur is not None and is_refs(text)          # shloka list carried onto the next line
        if not label and not refs_only and b.name != "li" and ((b.name != "p") if use_headings else is_bold_line(b)):
            drop_empty_label()
            title = re.sub(r"^\s*\d+\s*[.)]\s*", "", text)     # "1. People act …" -> "People act …"
            cur = {"title": plain(title), "intro": [], "refs": []}
            themes.append(cur)
        elif cur is None:
            continue                                           # anything before the first theme
        elif label or refs_only:
            drop_empty_label()
            if label:
                text = label.group(1)
            for m in REF.finditer(text):
                ch, a, z = int(m.group(1)), int(m.group(2)), int(m.group(3) or m.group(2))
                for v in range(a, max(a, z) + 1):
                    r = f"{ch}.{v}"
                    if r not in cur["refs"]:
                        cur["refs"].append(r)
        elif b.name == "li":                                   # "This teaches:" bullet points
            cur["intro"].append("<li>" + html.escape(plain(text), quote=False))
        else:
            cur["intro"].append(html.escape(plain(text), quote=False))
    drop_empty_label()
    # Themes with no shloka numbers yet stay in the data but get no page (build skips them).
    seen = set()
    for t in themes:
        s = base = slugify(t["title"])
        k = 2
        while s in seen:
            s, k = f"{base}-{k}", k + 1
        seen.add(s)
        t["slug"] = s
    return themes


# ---------------------------------------------------------------- geeta-themes.json -> pages
def load():
    return json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else []


def chapter_main(n):
    page = WORK / f"ch-{n}" / "index.html"
    if not page.exists():
        return None
    m = re.search(r'<main[^>]*id="content"[^>]*>(.*?)</main>', page.read_text(encoding="utf-8"), re.S)
    return m.group(1) if m else None


def shloka_parts(main, ref):
    """(shloka <p> html, simple-meaning <p> html) for ref '9.22' in a chapter's <main>."""
    paras = re.findall(r"<p\b[^>]*>.*?</p>", main, re.S)
    centred = lambda p: re.match(r'<p\b[^>]*text-align:\s*center', p) is not None
    target = re.compile(r"॥\s*" + re.escape(ref) + r"(?:\s*[-–]\s*\d+)?\s*॥")
    for i, p in enumerate(paras):
        if centred(p) and target.search(p):
            meaning = ""
            for q in paras[i + 1:]:
                if centred(q):
                    break
                if re.match(r"\s*simple\s+meaning", re.sub(r"<[^>]+>", "", q), re.I):
                    meaning = q
                    break
            return p, meaning
    return None, None


def build(helpers):
    """helpers: render_chrome, fill (from build.py)."""
    themes = load()
    by_ch = {}                                              # chapter n -> {ref: [(slug, title)]}
    if OUT.exists():
        shutil.rmtree(OUT)
    if not themes or not WORK.exists():
        _chapter_tags(by_ch)
        _index_link(False)
        return []
    render_chrome, fill = helpers["render_chrome"], helpers["fill"]
    mains = {}
    pages = []                                              # (path, url_path, title, desc) for seo
    built = []
    for t in themes:
        items = []
        for ref in t["refs"]:
            ch = int(ref.split(".")[0])
            if ch not in mains:
                mains[ch] = chapter_main(ch)
            if not mains[ch]:
                continue                                    # chapter not on the site yet
            verse, meaning = shloka_parts(mains[ch], ref)
            if not verse:
                continue
            items.append((ref, ch, verse, meaning))
            by_ch.setdefault(ch, {}).setdefault(ref, []).append((t["slug"], t["title"]))
        built.append((t, items))
    OUT.mkdir(parents=True, exist_ok=True)

    crumb = lambda href, label: f'    <a class="crumb" href="{href}">↩ {label}</a>\n'
    hero = lambda crumb_html, title, sub: (
        '  <section class="hero">\n' + crumb_html + '    <div class="om-large">ॐ</div>\n'
        f'    <h1>{html.escape(title)}</h1>\n' + (f'    <p class="subtitle">{html.escape(sub)}</p>\n' if sub else '')
        + '    <div class="divider"><span class="om">ॐ</span></div>\n  </section>\n')

    # all themes
    cards = "\n".join(
        f'      <a class="theme-card" href="{t["slug"]}/"><span class="theme-name">{html.escape(t["title"])}</span>'
        f'<span class="theme-count">{len(items)} shloka{"" if len(items) == 1 else "s"}</span></a>'
        for t, items in built if items)
    main = ('  <main class="content themes-page" id="content">\n'
            '    <p class="themes-lead">Shlokas that speak of the same idea, gathered from across the chapters.</p>\n'
            f'    <div class="theme-list">\n{cards}\n    </div>\n  </main>\n')
    title = "Themes — Bhagavad Geeta"
    desc = ("Bhagavad Geeta themes: shlokas on the same idea gathered across chapters — "
            + ", ".join(t["title"] for t, items in built if items) + ".")
    page = render_chrome(f"{title} | Samskrita Svadhyaya", html.escape(desc), "../../",
                         hero(crumb("../", "Bhagavad Geeta"), "Themes", "Bhagavad Geeta"), main)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    pages.append(("bhagavad-geeta/themes/index.html", "bhagavad-geeta/themes/", title + " | Samskrita Svadhyaya", desc))

    # one page per theme
    for t, items in built:
        if not items:
            continue
        intro = ""
        for i, p in enumerate(t["intro"]):
            prev_li = i > 0 and t["intro"][i - 1].startswith("<li>")
            next_li = i + 1 < len(t["intro"]) and t["intro"][i + 1].startswith("<li>")
            if p.startswith("<li>"):
                intro += ("    <ul>\n" if not prev_li else "") + f"      <li>{p[4:]}</li>\n" \
                    + ("    </ul>\n" if not next_li else "")
            else:
                intro += f"    <p>{p}</p>\n"
        body = []
        for ref, ch, verse, meaning in items:
            body.append(
                f'    <section class="theme-shloka" id="shloka-{ref}">\n'
                f'      <a class="theme-ref" href="../../ch-{ch}/#shloka-{ref}">Chapter {ch} · Shloka {ref} →</a>\n'
                f'      {verse}\n      {meaning}\n    </section>')
        main = ('  <main class="content theme-page" id="content">\n'
                + (f'    <div class="theme-intro">\n{intro}    </div>\n' if intro else "")
                + "\n".join(body) + "\n  </main>\n")
        desc = (html.unescape(re.sub(r"<[^>]+>", "", " ".join(t["intro"])))[:160] + " — " if t["intro"] else "") \
            + f'{t["title"]}: Bhagavad Geeta shlokas ' + ", ".join(r for r, *_ in items) + " with their meaning."
        page = render_chrome(f'{t["title"]} — Bhagavad Geeta themes | Samskrita Svadhyaya', html.escape(desc), "../../../",
                             hero(crumb("../", "Themes"), t["title"], "Bhagavad Geeta"), main)
        d = OUT / t["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page, encoding="utf-8")
        pages.append((f"bhagavad-geeta/themes/{t['slug']}/index.html", f"bhagavad-geeta/themes/{t['slug']}/",
                      f'{t["title"]} — Bhagavad Geeta themes | Samskrita Svadhyaya', desc))
    _chapter_tags(by_ch)
    _index_link(any(items for _, items in built))
    return pages


TAG = re.compile(r'\n?\s*<script type="application/json" id="shloka-themes">.*?</script>', re.S)


def _chapter_tags(by_ch):
    """Which shlokas of each chapter are in which themes (read by script.js)."""
    for page in WORK.glob("ch-*/index.html") if WORK.exists() else []:
        n = int(page.parent.name.split("-")[1])
        text = page.read_text(encoding="utf-8")
        new = TAG.sub("", text)
        data = {ref: [{"s": s, "t": t} for s, t in v] for ref, v in by_ch.get(n, {}).items()}
        if data:
            nl = "\r\n" if "\r\n" in text else "\n"
            new = new.replace("</head>", '  <script type="application/json" id="shloka-themes">'
                              + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + f"</script>{nl}</head>", 1)
        if new != text:
            page.write_text(new, encoding="utf-8")


LINK = re.compile(r"\s*<!-- themes-link -->.*?<!-- /themes-link -->", re.S)


def _index_link(on):
    """A "Themes" link on the Bhagavad Geeta page, above the chapter list."""
    page = WORK / "index.html"
    if not page.exists():
        return
    text = page.read_text(encoding="utf-8")
    new = LINK.sub("", text)
    if on:
        new = new.replace('<div class="chapter-grid">',
                          '<!-- themes-link --><p class="themes-link"><a href="themes/">Themes</a> — shlokas on the same idea, '
                          'gathered across chapters</p><!-- /themes-link -->\n    <div class="chapter-grid">', 1)
    if new != text:
        page.write_text(new, encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 3 and sys.argv[1] == "import":
        themes = parse_doc(sys.argv[2])
        DATA.write_text(json.dumps(themes, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for t in themes:
            print(f"{t['title']}: {', '.join(t['refs'])}")
        print(f"{len(themes)} theme(s) -> {DATA.name}; now run: python build.py home")
    elif len(sys.argv) >= 2 and sys.argv[1] == "build":
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "build.py"), "home"], check=True)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
