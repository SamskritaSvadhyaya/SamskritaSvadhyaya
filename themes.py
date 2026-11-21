#!/usr/bin/env python3
"""Themes: shlokas on one idea, gathered across chapters AND texts.

Source: the owner's Google Doc "Geeta Themes" (Drive folder "Bhagavad Geeta"; any title ending in
"Themes" works). Each theme is a heading (or a bold line), optionally a few lines of introduction /
"This teaches:" bullet points, then the shloka numbers, each with a short label for its text:

    Surrender to the Lord
    "Take refuge in Him alone"
    Shlokas: BG 18.66, 9.34, SK 38.33, N 32.4, SB 10.11.5

  BG  Bhagavad Geeta (the default: a number with no label is a Geeta shloka)
  N   Narayaneeyam                    32.4  (dashaka.shloka)
  SB  Shrimad Bhagavatam Canto 10     10.11.5 or 11.5
  SK  Sundarakanda                    5.38.33 or 38.33     (KK = Kishkindhakanda, YK = Yudhdhakanda,
  VR  any Valmiki Ramayana number     5.38.33)             KK 28.x finds the Eclectic Collection sarga)
  RV  Raghuvamsha                     12.3
  GA  Shri Ganapati Atharvashirsha    5
A number without a label takes the label before it on the same line ("SK 38.33, 38.40");
at the start of a line it means the Geeta. Ranges: "9.26-27", "SK 38.33-35".

  python themes.py import <download.json>   # doc (HTML export) -> themes.json, then build
  python themes.py build                    # pages only (also run by `build.py home`)

Pages (public): themes/ (all themes) and themes/<slug>/ - every shloka in full with its simple
meaning, read from the chapter pages, linked to it, grouped by text. Shlokas of chapters not on the
site yet are left out until the chapter is published. The old bhagavad-geeta/themes/ addresses
redirect here. Each chapter page with themed shlokas gets <script id="shloka-themes">; script.js
shows "Theme: …" under those shlokas. The home page and the Geeta page link to themes/.
"""
import base64
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "themes.json"
OUT = ROOT / "themes"
OLD = ROOT / "bhagavad-geeta" / "themes"               # earlier address: redirect stubs only
SITE = "https://samskritasvadhyaya.github.io/SamskritaSvadhyaya/"

# label -> (texts to look in, number prefix added when the number is written short, how many parts a full number has)
LABELS = {
    "BG": (["bhagavad-geeta"], "", 2),
    "N": (["narayaneeyam"], "", 2),
    "SB": (["shrimad-bhagavatam-canto-10"], "10.", 3),
    "SK": (["thestoryofhanuman"], "5.", 3),
    "KK": (["thestoryofhanuman", "eclectic-collection"], "4.", 3),
    "YK": (["thestoryofhanuman"], "6.", 3),
    "VR": (["thestoryofhanuman", "eclectic-collection"], "", 3),
    "RV": (["raghuvamsha"], "", 2),
    "GA": (["ganapati-atharvashirsha"], "", 1),
}
ALIASES = {"GITA": "BG", "GEETA": "BG", "NA": "N", "NAR": "N", "BHAG": "SB", "R": "VR", "RAM": "VR",
           "RAGHU": "RV", "GAN": "GA"}
REF = re.compile(r"(?:\b([A-Za-z]{1,6})\.?\s*)?(\d{1,3}(?:\s*\.\s*\d{1,3}){0,2})(?:\s*[-–]\s*(\d{1,3}))?")


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "theme"
    if len(s) > 60:                                     # a sentence-long heading: keep the address short
        s = s[:61].rsplit("-", 1)[0]
    return s


def label_of(word):
    w = (word or "").upper()
    return ALIASES.get(w, w) if (ALIASES.get(w, w) in LABELS) else None


def refs_in(text, problems=None):
    """['BG 9.22', 'SK 5.38.33', …] from one line of the doc."""
    out, cur = [], "BG"
    for m in REF.finditer(text):
        word, num, end = m.group(1), re.sub(r"\s+", "", m.group(2)), m.group(3)
        if word:
            lab = label_of(word)
            if lab is None:
                if problems is not None:
                    problems.append(f"unknown label '{word}' in: {text}")
                continue
            cur = lab
        _, prefix, parts = LABELS[cur]
        if num.count(".") + 1 == parts - prefix.count("."):
            num = prefix + num                                  # "SK 38.33" -> "5.38.33"
        if num.count(".") + 1 != parts:
            if problems is not None:
                problems.append(f"'{m.group(0).strip()}' doesn't look like a {cur} shloka number")
            continue
        head, last = (num.rsplit(".", 1) + [""])[:2] if "." in num else ("", num)
        a, z = int(last), int(end or last)
        for v in range(a, max(a, z) + 1):
            r = f"{cur} {head + '.' if head else ''}{v}"
            if r not in out:
                out.append(r)
    return out


# ---------------------------------------------------------------- doc -> themes.json
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
        if not REF.search(text) or not re.search(r"\d", text):
            return False
        rest = REF.sub(lambda m: "" if (not m.group(1) or label_of(m.group(1))) else m.group(0), text)
        return not re.sub(r"[\s,;.&]|and", "", rest, flags=re.I)

    def is_bold_line(b):
        t = b.get_text(" ", strip=True)
        if not t or len(t) > 250:                         # a heading can be a whole sentence
            return False
        spans = [s for s in b.find_all("span") if s.get_text(strip=True)]
        return spans and all(re.search(r"font-weight\s*:\s*(700|bold)", s.get("style", "")) for s in spans)

    themes, cur, problems = [], None, []
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
            for r in refs_in(label.group(1) if label else text, problems):
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
    return themes, problems


# ---------------------------------------------------------------- themes.json -> pages
def load():
    data = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else []
    for t in data:                                         # older data: plain "9.22" = Geeta
        t["refs"] = [r if " " in r else f"BG {r}" for r in t["refs"]]
    return data


def chapters():
    """{text key: (text title, [chapter dict from verses.json])}; built by build.py verse_index."""
    f = ROOT / "verses.json"
    data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    return {t["k"]: (t["t"], t["c"]) for t in data}


def page_main(rel):
    page = ROOT / rel / "index.html"
    if not page.exists():
        return None
    m = re.search(r'<main[^>]*id="content"[^>]*>(.*?)</main>', page.read_text(encoding="utf-8"), re.S)
    return m.group(1) if m else None


def shloka_parts(main, num):
    """(shloka <p> html, simple-meaning <p> html) for printed number '9.22' in a page's <main>."""
    paras = re.findall(r"<p\b[^>]*>.*?</p>", main, re.S)
    centred = lambda p: re.match(r'<p\b[^>]*text-align:\s*center', p) is not None
    head, last = num.rsplit(".", 1) if "." in num else ("", num)
    # the number itself, or a printed range that contains it (॥9.26-27॥)
    target = re.compile(r"॥\s*" + (re.escape(head) + r"\." if head else "") + r"(\d+)(?:\s*[-–]\s*(\d+))?\s*॥")

    def has(p):
        for m in target.finditer(p):
            a, z = int(m.group(1)), int(m.group(2) or m.group(1))
            if a <= int(last) <= z:
                return m.group(0).strip("॥ ")
        return None

    for i, p in enumerate(paras):
        printed = centred(p) and has(p)
        if printed:
            meaning = ""
            for q in paras[i + 1:]:
                if centred(q):
                    break
                if re.match(r"\s*simple\s+meaning", re.sub(r"<[^>]+>", "", q), re.I):
                    meaning = q
                    break
            return p, meaning, printed
    return None, None, None


def short_text(title):
    return title.split(" — ")[0]


def build(helpers):
    """helpers: render_chrome, fill (from build.py)."""
    themes = load()
    tagged = {}                                             # chapter path -> {printed number: [(slug, title)]}
    for d in (OUT, OLD):
        if d.exists():
            shutil.rmtree(d)
    if not themes:
        _chapter_tags(tagged)
        _links(False)
        return []
    render_chrome = helpers["render_chrome"]
    texts = chapters()
    mains = {}
    pages = []                                              # (path, url_path, title, desc) for seo
    built = []
    for t in themes:
        items = []                                          # (text title, chapter dict, printed, verse, meaning)
        for ref in t["refs"]:
            lab, num = ref.split(" ", 1)
            keys, _, _ = LABELS.get(lab, ([], "", 0))
            pre = num.rsplit(".", 1)[0] + "." if "." in num else ""
            found = None
            for k in keys:
                for c in texts.get(k, ("", []))[1]:
                    if c.get("pre", "") == pre:
                        found = (texts[k][0], c)
                        break
                if found:
                    break
            if not found:
                continue                                    # chapter not on the site (yet)
            title, c = found
            rel = c["p"].rstrip("/")
            if rel not in mains:
                mains[rel] = page_main(rel)
            if not mains[rel]:
                continue
            verse, meaning, printed = shloka_parts(mains[rel], num)
            if not verse or any(x[2] == printed and x[1] is c for x in items):
                continue                                    # not found, or the same printed range twice
            items.append((title, c, printed, verse, meaning))
            tagged.setdefault(c["p"], {}).setdefault(printed, []).append((t["slug"], t["title"]))
        built.append((t, items))
    OUT.mkdir(parents=True, exist_ok=True)

    crumb = lambda href, label: f'    <a class="crumb" href="{href}">↩ {label}</a>\n'
    hero = lambda crumb_html, title, sub: (
        '  <section class="hero">\n' + crumb_html + '    <div class="om-large">ॐ</div>\n'
        f'    <h1>{html.escape(title)}</h1>\n' + (f'    <p class="subtitle">{html.escape(sub)}</p>\n' if sub else '')
        + '    <div class="divider"><span class="om">ॐ</span></div>\n  </section>\n')
    texts_of = lambda items: list(dict.fromkeys(short_text(x[0]) for x in items))

    # all themes
    cards = "\n".join(
        f'      <a class="theme-card" href="{t["slug"]}/"><span class="theme-name">{html.escape(t["title"])}</span>'
        f'<span class="theme-count">{len(items)} shloka{"" if len(items) == 1 else "s"}'
        f'{" · " + html.escape(", ".join(texts_of(items))) if len(texts_of(items)) > 1 else ""}</span></a>'
        for t, items in built if items)
    main = ('  <main class="content themes-page" id="content">\n'
            '    <p class="themes-lead">Shlokas that speak of the same idea, gathered from across the chapters and texts.</p>\n'
            f'    <div class="theme-list">\n{cards}\n    </div>\n  </main>\n')
    title = "Themes"
    all_texts = list(dict.fromkeys(x for _, items in built for x in texts_of(items)))
    desc = ("Themes: Sanskrit shlokas on the same idea gathered across chapters and texts ("
            + ", ".join(all_texts) + ") — " + ", ".join(t["title"] for t, items in built if items) + ".")
    page = render_chrome(f"{title} | Samskrita Svadhyaya", html.escape(desc), "../",
                         hero(crumb("../", "Home"), "Themes", " · ".join(all_texts)), main)
    (OUT / "index.html").write_text(_private(page), encoding="utf-8")
    pages.append(("themes/index.html", "themes/", title + " | Samskrita Svadhyaya", desc))

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
        names = texts_of(items)
        body = []
        for name in names:                                  # grouped by text, in the doc's order
            if len(names) > 1:
                body.append(f'    <h2 class="theme-text">{html.escape(name)}</h2>')
            for title_, c, printed, verse, meaning in (x for x in items if short_text(x[0]) == name):
                part = f'{c["g"]} · ' if c.get("g") and not c["g"].startswith("Book") else ""
                where = f"{part}{c['l']} · " if c["l"] != title_ else ""
                body.append(
                    f'    <section class="theme-shloka" id="shloka-{html.escape(printed)}">\n'
                    f'      <a class="theme-ref" href="../../{c["p"]}#shloka-{html.escape(printed)}">'
                    f'{html.escape(where)}Shloka {html.escape(printed)} →</a>\n'
                    f'      {verse}\n      {meaning}\n    </section>')
        main = ('  <main class="content theme-page" id="content">\n'
                + (f'    <div class="theme-intro">\n{intro}    </div>\n' if intro else "")
                + "\n".join(body) + "\n  </main>\n")
        desc = (html.unescape(re.sub(r"<[^>]+>", "", " ".join(t["intro"])))[:160] + " — " if t["intro"] else "") \
            + f'{t["title"]}: shlokas from ' + ", ".join(names) + " (" + ", ".join(x[2] for x in items) + ") with their meaning."
        page = render_chrome(f'{t["title"]} — Themes | Samskrita Svadhyaya', html.escape(desc), "../../",
                             hero(crumb("../", "Themes"), t["title"], " · ".join(names)), main)
        d = OUT / t["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(_private(page), encoding="utf-8")
        pages.append((f"themes/{t['slug']}/index.html", f"themes/{t['slug']}/",
                      f'{t["title"]} — Themes | Samskrita Svadhyaya', desc))
    _redirects([t["slug"] for t, items in built if items])
    _chapter_tags(tagged)
    _links(any(items for _, items in built))
    return pages


OWNER_ONLY = True       # owner's choice (2026-11-20): Themes only for the site owner for now.
                        # Going public: set False here AND THEMES_OWNER_ONLY = false in script.js.


def _private(html_page):
    """Owner-only theme page: not indexed, hidden by CSS unless the site owner is signed in."""
    if not OWNER_ONLY:
        return html_page
    return (html_page.replace('<html lang="en">', '<html lang="en" class="owner-only-page">', 1)
                     .replace("</head>", '  <meta name="robots" content="noindex" />\n</head>', 1))


def _redirects(slugs):
    """bhagavad-geeta/themes/… (the first address of these pages) -> themes/…"""
    for rel in ["", *[s + "/" for s in slugs]]:
        url = SITE + "themes/" + rel
        d = OLD / rel
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(
            '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>Moved — Themes</title>\n'
            f'<link rel="canonical" href="{url}">\n<meta name="robots" content="noindex">\n'
            f'<meta http-equiv="refresh" content="0; url={url}">\n'
            f'<script>location.replace("{url}" + location.hash);</script>\n</head>\n<body>\n'
            f'<p>This page has moved to <a href="{url}">{url}</a>.</p>\n</body>\n</html>\n', encoding="utf-8")


TAG = re.compile(r'\n?\s*<script type="application/json" id="shloka-themes">.*?</script>', re.S)


def _chapter_tags(tagged):
    """Which shlokas of each chapter are in which themes (read by script.js)."""
    for _, (_, chs) in chapters().items():
        for c in chs:
            page = ROOT / c["p"] / "index.html"
            if not page.exists():
                continue
            text = page.read_text(encoding="utf-8")
            new = TAG.sub("", text)
            data = {ref: [{"s": s, "t": t} for s, t in v] for ref, v in tagged.get(c["p"], {}).items()}
            if data:
                nl = "\r\n" if "\r\n" in text else "\n"
                new = new.replace("</head>", '  <script type="application/json" id="shloka-themes">'
                                  + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + f"</script>{nl}</head>", 1)
            if new != text:
                page.write_text(new, encoding="utf-8")


LINK = re.compile(r"\s*<!-- themes-link -->.*?<!-- /themes-link -->", re.S)


def _links(on):
    """"Themes" link on the Bhagavad Geeta page. (The home page one, under the texts, was removed at the
    owner's request 2026-11-20 - the header has a Themes button; LINK.sub still clears it from index.html.)"""
    spots = [
        (ROOT / "index.html", "<!-- home-themes -->", None),
        (ROOT / "bhagavad-geeta" / "index.html", '<div class="chapter-grid">',
         '<p class="themes-link"><a href="../themes/">Themes</a> — shlokas on the same idea, '
         'gathered across chapters and texts</p>'),
    ]
    for page, anchor, link in spots:
        if not page.exists():
            continue
        text = page.read_text(encoding="utf-8")
        new = LINK.sub("", text)
        if on and link and anchor in new:
            block = f"<!-- themes-link -->{link}<!-- /themes-link -->"
            new = new.replace(anchor, (anchor + block) if anchor.startswith("<!--") else (block + "\n    " + anchor), 1)
        if new != text:
            page.write_text(new, encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 3 and sys.argv[1] == "import":
        themes, problems = parse_doc(sys.argv[2])
        DATA.write_text(json.dumps(themes, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for t in themes:
            print(f"{t['title']}: {', '.join(t['refs'])}")
        for p in problems:
            print("  ! " + p)
        print(f"{len(themes)} theme(s) -> {DATA.name}; now run: python build.py home")
    elif len(sys.argv) >= 2 and sys.argv[1] == "build":
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "build.py"), "home"], check=True)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
