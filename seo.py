#!/usr/bin/env python3
"""Search-engine metadata for every published page, plus sitemap.xml.

For each page listed in texts.json this sets a descriptive <title> and
<meta name="description"> (work, chapter number and subject, in English and
Sanskrit), and adds a canonical URL and Open Graph / Twitter link-preview tags
inside a <!-- seo --> block in <head>. It then writes sitemap.xml listing every
published page. Idempotent; build.py runs it after every `home` build.

Usage:
    python3 seo.py
"""

import html
import json
import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "texts.json"
SITE = "https://samskritasvadhyaya.github.io/SamskritaSvadhyaya/"
NAME = "Samskrita Svadhyaya"
TAGLINE = "Sanskrit verses (shlokas) with word-by-word meaning, anvaya and English translation."
BEGIN, END = "<!-- seo -->", "<!-- /seo -->"

_DEV = re.compile(r"[ऀ-ॿ]")
_CENTRED = re.compile(r'<p style="text-align:center">(.*?)</p>', re.S)
_UNIT = {"sarga": "Sarga", "dashaka": "Dashaka", "ch": "Chapter"}


def plain(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def short(title):
    return title.split(" — ")[0].strip()


def subject_of(page_html, skip):
    """The chapter's subject line: the first centred English heading above the
    verses that isn't a number heading ("Sarga 2", "Canto 10") or a work name."""
    body = page_html.split('id="content">', 1)[-1]
    lines = []
    for inner in _CENTRED.findall(body):
        if "#274e13" in inner:  # first verse reached
            break
        lines.append((plain(inner), "<img" in inner))

    def english(text, img):
        return bool(text) and not img and not _DEV.search(text) and not text.startswith("(")

    for i, (text, img) in enumerate(lines):
        if (not english(text, img) or re.search(r"\d", text) or text.lower().strip(" .") in skip):
            continue
        # A heading typed over two lines ("…Daily Routine and" / "the sending of…"):
        # join the next line when this one ends in a joining word or the next starts lowercase.
        for nxt, nimg in lines[i + 1:]:
            if not english(nxt, nimg) or re.search(r"\d", nxt):
                break
            if not (_JOINER.search(text) or nxt[:1].islower()):
                break
            text = f"{text} {nxt}"
        return text.rstrip(" .")
    return ""


_JOINER = re.compile(r"\b(and|or|of|the|to|with|by|in|for|from|at|on|a|an|as)\s*$", re.I)


def attr(value):
    return html.escape(value, quote=True)


def brief(text, limit=90):
    """First sentence, cut at a word boundary — keeps search titles readable."""
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0].rstrip(" .")
    if len(first) <= limit:
        return first
    return first[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def intro_of(entry):
    """First paragraph of a collection's introduction (note_html), if any."""
    for p in re.findall(r"<p>(.*?)</p>", entry.get("note_html", ""), re.S):
        text = plain(p)
        if len(text) > 40 and not _DEV.search(text[:20]):
            return text
    return ""


def skip_set(entries):
    """Collection/work names that a chapter's subject line can't be."""
    skip = {NAME.lower()}
    for e in entries:
        skip |= {e["title"].lower(), short(e["title"]).lower()}
        for w in e.get("works", []):
            skip |= {w["title"].lower(), short(w["title"]).lower()}
    return skip


def chapter_subject(page_or_body, entries, chapter_title):
    """Subject line of a chapter (e.g. "Hanuman crosses the ocean, reaches Lanka"),
    or "" when there is none or it merely repeats the chapter's own title."""
    subj = subject_of(page_or_body, skip_set(entries))
    return "" if subj.lower() == chapter_title.strip().lower() else subj


def pages():
    """Yield (path, url_path, info) for every published page."""
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    skip = skip_set(entries)

    yield "index.html", "", {
        "title": f"{NAME} — Sanskrit texts with meaning, anvaya and translation",
        "desc": "A self-study library of Sanskrit texts: Valmiki Ramayana (Sundarakanda), "
                "Narayaneeyam, Shrimad Bhagavatam, Kalidasa's Raghuvamsha, Ganapati "
                "Atharvashirsha and more. " + TAGLINE,
        "image": "og-image.png", "type": "website",
    }

    def collection(e, prefix, parent=None):
        sub = e.get("subtitle") or brief(intro_of(e), 200)
        name = short(e["title"])
        sa = e.get("title_sa", "")
        if parent is not None:
            ptitle = short(parent["title"])
            title = f"{name} ({sa}) — {ptitle} | {NAME}"
            desc = f"{name} from {parent['title']}" + (f": {sub}" if sub else "") + f". {TAGLINE}"
        else:
            title = f"{e['title']} ({sa}) | {NAME}"
            desc = f"{e['title']}" + (f" — {sub}" if sub else "") + f". {TAGLINE}"
        return {"title": title, "desc": desc, "image": e.get("image") or "", "type": "website"}

    def chapters(work, prefix, parent=None):
        wname, wsa = short(work["title"]), work.get("title_sa", "")
        if parent is not None and wname.lower().startswith("book"):
            wname = parent["title"].replace(" — ", " ")
            wsa = parent.get("title_sa", "").replace(" · ", " ")
        collection_name = parent["title"] if parent is not None else work["title"]
        for c in work.get("chapters", []):
            path = f"{prefix}{c['slug']}/index.html"
            f = ROOT / path
            if not f.exists():
                continue
            m = re.fullmatch(r"(sarga|dashaka|ch)-(\d+)", c["slug"])
            if m:
                base = f"{wname} {_UNIT[m.group(1)]} {m.group(2)}"
                sa = f"{wsa} {c.get('title_sa', '')}".strip()
            else:
                base, sa = c["title"], c.get("title_sa", "")
            subj = c.get("subject") or subject_of(f.read_text(encoding="utf-8"), skip)
            if not subj and m and c["title"] != base.split(" ", 1)[-1] and not re.search(r"\d", c["title"]):
                subj = c["title"]  # e.g. Narayaneeyam: the chapter title is the subject
            head = f"{base}: {subj}" if subj else base
            yield path, f"{prefix}{c['slug']}/", {
                "title": f"{base}: {subj} — {sa} | {NAME}" if subj else f"{base} — {sa} | {NAME}",
                "desc": f"{head.rstrip('.')}, from {collection_name}. {TAGLINE}",
                "image": c.get("image") or work.get("image") or (parent or {}).get("image") or "",
                "type": "article",
            }

    for e in entries:
        p = f"{e['slug']}/"
        if e.get("type") == "parent":
            yield f"{p}index.html", p, collection(e, p)
            for w in e.get("works", []):
                wp = f"{p}{w['slug']}/"
                yield f"{wp}index.html", wp, collection(w, wp, parent=e)
                yield from chapters(w, wp, parent=e)
        elif e.get("chapters") is not None or e.get("type") == "work":
            yield f"{p}index.html", p, collection(e, p)
            yield from chapters(e, p)
        else:  # standalone text
            info = collection(e, p)
            info["title"] = f"{e['title']} ({e.get('title_sa', '')}) — with word-by-word meaning, anvaya and translation | {NAME}"
            yield f"{p}index.html", p, info


def apply(path, url_path, info):
    f = ROOT / path
    if not f.exists():
        return False
    s = f.read_text(encoding="utf-8")
    url = SITE + url_path
    desc = info["desc"][:300]
    # Pages without a picture of their own share the ॐ preview picture.
    image = SITE + (info.get("image") or "og-image.png")
    tags = [
        f'<link rel="canonical" href="{attr(url)}" />',
        f'<meta property="og:site_name" content="{attr(NAME)}" />',
        f'<meta property="og:type" content="{info["type"]}" />',
        f'<meta property="og:title" content="{attr(info["title"].rsplit(" | ", 1)[0])}" />',
        f'<meta property="og:description" content="{attr(desc)}" />',
        f'<meta property="og:url" content="{attr(url)}" />',
    ]
    if image:
        tags.append(f'<meta property="og:image" content="{attr(image)}" />')
    tags.append(f'<meta name="twitter:card" content="{"summary_large_image" if image else "summary"}" />')
    block = BEGIN + "\n  " + "\n  ".join(tags) + "\n  " + END

    t = re.sub(r"\s*" + re.escape(BEGIN) + r".*?" + re.escape(END), "", s, flags=re.S)
    t = re.sub(r"<title>.*?</title>", lambda _: f"<title>{html.escape(info['title'], quote=False)}</title>", t, count=1, flags=re.S)
    t = re.sub(r'<meta name="description" content="[^"]*" />', lambda _: f'<meta name="description" content="{attr(desc)}" />', t, count=1)
    t = t.replace("</head>", f"  {block}\n</head>", 1)
    if t != s:
        f.write_text(t, encoding="utf-8")
    return True


def lastmods():
    """Last commit date of each file (one git call); uncommitted files get today."""
    try:
        out = subprocess.run(["git", "log", "--format=@%cs", "--name-only"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    seen, day = {}, None
    for line in out.splitlines():
        if line.startswith("@"):
            day = line[1:]
        elif line and line not in seen:
            seen[line] = day
    return seen


def main():
    dates = lastmods()
    dirty = set()
    try:
        dirty = set(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                                   text=True, encoding="utf-8").stdout.split("\n"))
        dirty = {l[3:].strip() for l in dirty if l.strip()}
    except OSError:
        pass
    today = date.today().isoformat()
    urls = []
    for path, url_path, info in pages():
        if apply(path, url_path, info):
            mod = today if any(path.startswith(d.rstrip("/")) for d in dirty) else dates.get(path, today)
            urls.append((SITE + url_path, mod))
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, mod in urls:
        xml.append(f"  <url><loc>{html.escape(loc)}</loc><lastmod>{mod}</lastmod></url>")
    xml.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(xml) + "\n", encoding="utf-8")
    # Same list as plain text (one URL per line) — also accepted by Google Search Console.
    (ROOT / "sitemap.txt").write_text("".join(f"{loc}\n" for loc, _ in urls), encoding="utf-8")
    print(f"SEO tags on {len(urls)} page(s); wrote sitemap.xml and sitemap.txt")


if __name__ == "__main__":
    main()
