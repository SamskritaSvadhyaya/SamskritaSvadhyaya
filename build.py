#!/usr/bin/env python3
"""Static-site generator for the Samskrita Svadhyaya text library.

The library (texts.json) holds three kinds of top-level entries:

  - "text":   a standalone text  -> /<slug>/index.html
  - "work":   a multi-chapter work -> /<slug>/index.html (chapter index)
                                       with chapters at /<slug>/<ch-slug>/index.html
  - "parent": a curated collection -> /<slug>/index.html (landing page)
                                      containing child works at /<slug>/<work-slug>/...
                                      and sargas at /<slug>/<work-slug>/<ch-slug>/...

Commands:

  build.py page --slug <s> [--work <w>] [--parent <p>] --title <t> --title-sa <sa>
                [--subtitle <s>] [--n <int>] --body <file.html>
      Wrap a content body in the site template. With --parent + --work, the page
      is a chapter under that parent's work; with --work alone, a chapter under a
      top-level work; with neither, a standalone text.

  build.py set-work --slug <s> [--parent <p>] --title <t> --title-sa <sa>
                    [--subtitle <s>] [--note <file.html>]
      Create/update a work entry (preserving its chapters), optionally inside a parent,
      optionally embedding an HTML note preamble above the chapter grid.

  build.py set-parent --slug <s> --title <t> --title-sa <sa> [--subtitle <s>]
                      [--note <file.html>]
      Create/update a parent entry, optionally embedding an HTML note preamble.

  build.py work-index --slug <s> [--parent <p>]
      Regenerate the chapter-index for a work (under a parent if specified).

  build.py parent-index --slug <s>
      Regenerate the landing page for a parent (Note preamble + child cards).

  build.py home
      Regenerate the root index.html (top-level card grid).
"""

import argparse
import json
import re
from html import escape as html_escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "texts.json"

FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "viewBox='0 0 64 64'%3E%3Ctext x='50%25' y='55%25' dominant-baseline='middle' "
    "text-anchor='middle' font-size='52' fill='%23c0392b'%3E%E0%A5%90%3C/text%3E%3C/svg%3E"
)
SLOGAN = "स्वाध्यायात् स्वाध्यायपर्यन्तम्"

HEADER = """  <div id="progress"></div>

  <div class="slogan-bar">
    <span class="slogan" lang="sa">""" + SLOGAN + """</span>
  </div>

  <header class="site-header">
    <div class="nav-inner">
      <a class="brand" href="{{REL}}index.html">
        <span class="om">ॐ</span>
        <span class="title">Samskrita Svadhyaya</span>
      </a>
      <div class="controls" role="toolbar" aria-label="Reading controls">
        <a class="home-link" href="{{REL}}index.html" title="All texts">⌂ Texts</a>
        <button id="size-down" title="Decrease font size" aria-label="Decrease font size">A−</button>
        <button id="size-up"   title="Increase font size" aria-label="Increase font size">A+</button>
        <button id="toggle-theme" aria-pressed="false" title="Toggle dark mode">☾ Dark</button>
      </div>
    </div>
  </header>
"""

FOOTER = """
  <footer class="site-footer">
    <span class="om">ॐ शान्तिः शान्तिः शान्तिः</span>
    <div>
      Rendered from the original documents via <a href="https://pandoc.org" target="_blank" rel="noopener">pandoc</a>.
      Source on <a href="https://github.com/SamskritaSvadhyaya/SamskritaSvadhyaya" target="_blank" rel="noopener">GitHub</a>.
    </div>
  </footer>

  <button id="to-top" title="Back to top" aria-label="Back to top">↑</button>

  <script src="{{REL}}script.js"></script>
</body>
</html>
"""

DOC_OPEN = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{HTML_TITLE}}</title>
  <meta name="description" content="{{DESC}}" />
  <link rel="icon" href=\"""" + FAVICON + """\" />
  <link rel="stylesheet" href="{{REL}}style.css" />
</head>
<body>
"""

PAGE_HERO = """
  <section class="hero">
{{BREADCRUMB}}    <div class="om-large">ॐ</div>
    <h1>{{TITLE}}</h1>
    <p class="subtitle">{{TITLE_SA}}{{SUBSEP}}{{SUBTITLE}}</p>
    <div class="divider"><span class="om">ॐ</span></div>
  </section>

  <main class="content" id="content">
"""

DEV_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")


def dev_num(n):
    return str(n).translate(DEV_DIGITS)


def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return []


def save_manifest(entries):
    MANIFEST.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def find_entry(entries, slug):
    for e in entries:
        if e.get("slug") == slug:
            return e
    return None


def find_parent(entries, slug):
    for e in entries:
        if e.get("slug") == slug and is_parent(e):
            return e
    return None


def find_work_in(works, slug):
    for w in works or []:
        if w.get("slug") == slug:
            return w
    return None


def is_work(entry):
    return entry.get("type") == "work" or "chapters" in entry


def is_parent(entry):
    return entry.get("type") == "parent" or "works" in entry


def clean_body(body):
    body = re.sub(r'src="[^"]*?/media/', 'src="media/', body)
    body = re.sub(r'\s*style="width:[^"]*"', "", body)
    return body


def first_image(body, rel_from_root):
    m = re.search(r'src="(?:\./)?media/([^"]+)"', body)
    return f"{rel_from_root}/media/{m.group(1)}" if m else None


def fill(template, **kw):
    out = template
    for key, val in kw.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def rel_for(depth):
    return "../" * depth


def render_chrome(title, desc, rel, hero, body_main):
    return (
        fill(DOC_OPEN, REL=rel, HTML_TITLE=title, DESC=desc)
        + HEADER.replace("{{REL}}index.html", rel or "./").replace("{{REL}}", rel)
        + hero
        + body_main
        + FOOTER.replace("{{REL}}", rel)
    )


def build_page(args):
    body = clean_body(Path(args.body).read_text(encoding="utf-8"))
    entries = load_manifest()

    if args.parent:
        if not args.work:
            raise SystemExit("--parent requires --work (chapter lives at parent/work/slug)")
        parent = find_parent(entries, args.parent)
        if parent is None:
            raise SystemExit(f"Run set-parent for '{args.parent}' first.")
        work = find_work_in(parent.get("works", []), args.work)
        if work is None:
            raise SystemExit(
                f"Run set-work --parent {args.parent} --slug {args.work} first."
            )
        depth = 3
        page_dir = ROOT / args.parent / args.work / args.slug
        rel_from_root = f"{args.parent}/{args.work}/{args.slug}"
        crumb = f'    <a class="crumb" href="../">↩ {work["title"]}</a>\n'
    elif args.work:
        work = find_entry(entries, args.work)
        if work is None or not is_work(work):
            raise SystemExit(f"Run set-work for '{args.work}' before adding chapters.")
        depth = 2
        page_dir = ROOT / args.work / args.slug
        rel_from_root = f"{args.work}/{args.slug}"
        crumb = f'    <a class="crumb" href="../">↩ {work["title"]}</a>\n'
    else:
        work = None
        depth = 1
        page_dir = ROOT / args.slug
        rel_from_root = args.slug
        crumb = ""

    rel = rel_for(depth)
    image = first_image(body, rel_from_root)
    # A chapter's short description (the subject line under its heading in the doc,
    # e.g. "Hanuman crosses the ocean, reaches Lanka") is shown under the page title
    # and on the chapter card, and used for search titles.
    subject = args.subject or ""
    if work is not None and not args.subtitle and not subject:
        import seo
        subject = seo.chapter_subject(body, entries, args.title)
    subtitle = args.subtitle or (html_escape(subject, quote=False) if subject else "")

    drop_label = work is not None and bool(subtitle)
    html = (
        fill(DOC_OPEN, REL=rel,
             HTML_TITLE=f"{args.title} — {args.title_sa}",
             DESC=f"{args.title} — Sanskrit text with word-by-word meaning, anvaya, and translation.")
        + HEADER.replace("{{REL}}index.html", rel or "./").replace("{{REL}}", rel)
        # A sarga/chapter with a description shows just the description under its heading
        # (no "सर्गः ७ ·" label).
        + fill(PAGE_HERO, BREADCRUMB=crumb, TITLE=args.title,
               TITLE_SA="" if drop_label else args.title_sa,
               SUBTITLE=subtitle, SUBSEP=" · " if (subtitle and not drop_label) else "")
        + body
        + "  </main>\n"
        + FOOTER.replace("{{REL}}", rel)
    )

    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "index.html").write_text(html, encoding="utf-8")

    chapter_entry = {
        "slug": args.slug,
        "title": args.title,
        "title_sa": args.title_sa,
        "n": args.n if args.n is not None else 0,
        "image": image,
    }
    if subject:
        chapter_entry["subject"] = subject
    if not chapter_entry.get("image"):
        chapter_entry.pop("image", None)   # the site shows no pictures

    if work is not None:
        chapters = [c for c in work.get("chapters", []) if c.get("slug") != args.slug]
        if chapter_entry["n"] == 0:
            chapter_entry["n"] = len(chapters) + 1
        chapters.append(chapter_entry)
        chapters.sort(key=lambda c: c.get("n", 0))
        work["chapters"] = chapters
    else:
        # Update a standalone text in place: keep its position on the home page and any other
        # settings (re-uploading used to re-sort every text alphabetically).
        fields = {"type": "text", "slug": args.slug, "title": args.title,
                  "title_sa": args.title_sa, "subtitle": subtitle}
        existing = find_entry(entries, args.slug)
        if existing is not None:
            existing.update(fields)
        else:
            entries.append(fields)

    save_manifest(entries)
    print(f"Wrote {rel_from_root}/index.html and updated texts.json")


def set_work(args):
    entries = load_manifest()
    if args.parent:
        parent = find_parent(entries, args.parent)
        if parent is None:
            raise SystemExit(f"Run set-parent for '{args.parent}' first.")
        work = find_work_in(parent.get("works", []), args.slug)
        if work is None:
            work = {"type": "work", "slug": args.slug, "chapters": []}
            parent.setdefault("works", []).append(work)
    else:
        work = find_entry(entries, args.slug)
        if work is None:
            work = {"type": "work", "slug": args.slug, "chapters": []}
            entries.append(work)
    work["type"] = "work"
    work["title"] = args.title
    work["title_sa"] = args.title_sa
    work["subtitle"] = args.subtitle or ""
    if args.note:
        work["note_html"] = Path(args.note).read_text(encoding="utf-8")
    work.setdefault("chapters", [])
    save_manifest(entries)
    print(f"Set work '{args.slug}'" + (f" under parent '{args.parent}'" if args.parent else ""))


def set_parent(args):
    entries = load_manifest()
    parent = find_parent(entries, args.slug)
    if parent is None:
        parent = {"type": "parent", "slug": args.slug, "works": []}
        entries.append(parent)
    parent["type"] = "parent"
    parent["title"] = args.title
    parent["title_sa"] = args.title_sa
    parent["subtitle"] = args.subtitle or ""
    if args.note:
        parent["note_html"] = Path(args.note).read_text(encoding="utf-8")
    parent.setdefault("works", [])
    save_manifest(entries)
    print(f"Set parent '{args.slug}'")


def build_work_index(args):
    entries = load_manifest()
    if args.parent:
        parent = find_parent(entries, args.parent)
        if parent is None:
            raise SystemExit(f"No parent '{args.parent}'.")
        work = find_work_in(parent.get("works", []), args.slug)
        if work is None or not is_work(work):
            raise SystemExit(f"No work '{args.slug}' under parent '{args.parent}'.")
        depth = 2
        out_dir = ROOT / args.parent / args.slug
        crumb = f'    <a class="crumb" href="../">↩ {parent["title"]}</a>\n'
    else:
        work = find_entry(entries, args.slug)
        if work is None or not is_work(work):
            raise SystemExit(f"No work named '{args.slug}'.")
        depth = 1
        out_dir = ROOT / args.slug
        crumb = '    <a class="crumb" href="../">↩ All texts</a>\n'

    rel = rel_for(depth)
    chapters = sorted(work.get("chapters", []), key=lambda c: c.get("n", 0))
    cards = "\n".join(
        """      <a class="chapter-card" href="{slug}/">
        <span class="chapter-num">{num}</span>
        <span class="chapter-meta">
          <span class="chapter-title-sa" lang="sa">{title_sa}</span>
          <span class="chapter-title">{title}</span>{subject}
        </span>
      </a>""".format(
            slug=c["slug"],
            num=dev_num(c.get("n", 0)),
            title_sa=c.get("title_sa", ""),
            title=c.get("title", ""),
            subject=(
                '\n          <span class="chapter-subject">{}</span>'.format(
                    html_escape(c["subject"], quote=False))
                if c.get("subject") else ""
            ),
        )
        for c in chapters
    ) or '      <p class="empty-note">No chapters yet.</p>'

    sub = work.get("subtitle", "")
    hero = fill(
        PAGE_HERO.replace('<main class="content" id="content">', '<main class="home">'),
        BREADCRUMB=crumb,
        TITLE=work["title"],
        TITLE_SA=work["title_sa"],
        SUBTITLE=sub,
        SUBSEP=" · " if sub else "",
    )
    note_html = work.get("note_html", "")
    preamble = (f'    <section class="preamble">\n{note_html}\n    </section>\n'
                if note_html else '')
    body_main = f'{preamble}    <div class="chapter-grid">\n{cards}\n    </div>\n  </main>\n'

    html = render_chrome(
        f'{work["title"]} — {work["title_sa"]}',
        f'{work["title"]} — chapter index',
        rel,
        hero,
        body_main,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    where = f"{args.parent}/{args.slug}" if args.parent else args.slug
    print(f"Wrote {where}/index.html ({len(chapters)} chapter(s))")


def build_parent_index(args):
    entries = load_manifest()
    parent = find_parent(entries, args.slug)
    if parent is None:
        raise SystemExit(f"No parent named '{args.slug}'.")

    rel = "../"
    works = parent.get("works", [])
    cards = "\n".join(
        """      <a class="text-card" href="{slug}/">
        <div class="card-emblem">ॐ</div>
        <div class="card-body">
          <span class="card-title-sa" lang="sa">{title_sa}</span>
          <span class="card-title">{title}</span>
          <span class="card-sub">{subtitle}</span>
        </div>
      </a>""".format(
            slug=w["slug"],
            title=w.get("title", ""),
            title_sa=w.get("title_sa", ""),
            subtitle=(w.get("subtitle") or
                      (f"{len(w.get('chapters', []))} sarga"
                       f"{'s' if len(w.get('chapters', [])) != 1 else ''}")),
        )
        for w in works
    ) or '      <p class="empty-note">No works yet.</p>'

    note_html = parent.get("note_html", "")
    preamble = (f'    <section class="preamble">\n{note_html}\n    </section>\n'
                if note_html else '')

    sub = parent.get("subtitle", "")
    hero = fill(
        PAGE_HERO.replace('<main class="content" id="content">', '<main class="home">'),
        BREADCRUMB='    <a class="crumb" href="../">↩ All texts</a>\n',
        TITLE=parent["title"],
        TITLE_SA=parent["title_sa"],
        SUBTITLE=sub,
        SUBSEP=" · " if sub else "",
    )
    body_main = f'{preamble}    <div class="home-grid">\n{cards}\n    </div>\n  </main>\n'

    html = render_chrome(
        f'{parent["title"]} — {parent["title_sa"]}',
        parent["title"],
        rel,
        hero,
        body_main,
    )
    (ROOT / args.slug).mkdir(parents=True, exist_ok=True)
    (ROOT / args.slug / "index.html").write_text(html, encoding="utf-8")
    print(f"Wrote {args.slug}/index.html (parent with {len(works)} work(s))")


def build_home(_args=None):
    entries = load_manifest()
    cards = []
    for e in entries:
        if is_parent(e):
            n_chap = sum(len(w.get("chapters", [])) for w in e.get("works", []))
            n_works = len(e.get("works", []))
            sub = e.get("subtitle") or ""   # no automatic "3 works · 73 sargas"
            emblem = (
                f'<img src="{e["image"]}" alt="" loading="lazy" />'
                if e.get("image") else "ॐ"
            )
        elif is_work(e):
            count = len(e.get("chapters", []))
            sub = e.get("subtitle") or ""   # no automatic "1 chapter"
            emblem = (
                f'<img src="{e["image"]}" alt="" loading="lazy" />'
                if e.get("image") else "ॐ"
            )
        else:
            sub = e.get("subtitle", "")
            emblem = (
                f'<img src="{e["image"]}" alt="" loading="lazy" />'
                if e.get("image") else "ॐ"
            )
        cards.append(
            """      <a class="text-card" href="{slug}/">
        <div class="card-emblem">{emblem}</div>
        <div class="card-body">
          <span class="card-title-sa" lang="sa">{title_sa}</span>
          <span class="card-title">{title}</span>
          <span class="card-sub">{subtitle}</span>
        </div>
      </a>""".format(
                slug=e["slug"],
                emblem=emblem,
                title_sa=e.get("title_sa", ""),
                title=e.get("title", ""),
                subtitle=sub,
            )
        )

    grid = "\n".join(cards) if cards else (
        """      <div class="text-card empty">
        <div class="card-emblem">ॐ</div>
        <div class="card-body"><span class="card-title">More texts coming soon</span></div>
      </div>"""
    )

    hero = """
  <section class="hero">
    <div class="om-large">ॐ</div>
    <h1>Samskrita Svadhyaya</h1>
    <p class="subtitle">A self-study library of Sanskrit texts — verses with meaning, anvaya, and translation</p>
    <div class="divider"><span class="om">ॐ</span></div>
  </section>

  <main class="home">
    <div class="home-grid">
"""
    body_main = hero + grid + "\n    </div>\n  </main>\n"

    html = render_chrome(
        "Samskrita Svadhyaya — Sanskrit Text Library",
        "A self-study library of Sanskrit texts: verses with word-by-word meaning, anvaya, and translation.",
        "",
        "",
        body_main,
    )
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    print(f"Wrote index.html (home) with {len(entries)} entr(y/ies)")

    build_static_pages()
    chapter_nav()
    verse_index()
    stamp_assets()

    # Every build flow ends with `home`, so refresh search metadata + sitemap here.
    import seo
    seo.main()


STATIC_HERO = """
  <section class="hero">
    <div class="om-large">ॐ</div>
    <h1>{{TITLE}}</h1>
    <p class="subtitle">{{SUBTITLE}}</p>
    <div class="divider"><span class="om">ॐ</span></div>
  </section>
"""


NAV_RE = re.compile(r"\s*<!-- chapter-nav -->.*?<!-- /chapter-nav -->", re.S)
UNITS = {"sarga": "sargas", "dashaka": "dashakas", "ch": "chapters"}


def chapter_nav():
    """Previous / Next buttons at the bottom of every chapter page, in texts.json order.
    Within a parent collection the sequence runs on across its works (Kishkindhakanda ->
    Sundarakanda -> Yudhdhakanda; Book 1 -> Book 2). Rewritten on every build, so new or
    re-imported chapters always get correct links."""
    import os

    def label(ch, work_title, cross):
        title, sub = ch.get("title", ""), ch.get("subject", "")
        if cross:
            title = f"{work_title} · {title}"
        return title, sub

    for top in load_manifest():
        if is_parent(top):
            seq = [(f"{top['slug']}/{w['slug']}", w.get("title", ""), c)
                   for w in top.get("works", []) for c in w.get("chapters", [])]
        elif is_work(top):
            seq = [(top["slug"], top.get("title", ""), c) for c in top.get("chapters", [])]
        else:
            continue
        for i, (work_dir, work_title, ch) in enumerate(seq):
            page = ROOT / work_dir / ch["slug"] / "index.html"
            if not page.exists():
                continue
            here = f"{work_dir}/{ch['slug']}"

            def link(j, cls, arrow_left):
                if not 0 <= j < len(seq):
                    return f'    <span class="cn-{cls} cn-empty"></span>\n'
                wd, wt, c = seq[j]
                href = os.path.relpath(f"{wd}/{c['slug']}", here).replace(os.sep, "/") + "/"
                title, sub = label(c, wt, wd != work_dir)
                word = "Previous" if arrow_left else "Next"
                return (f'    <a class="cn-{cls}" href="{html_escape(href)}" rel="{"prev" if arrow_left else "next"}">'
                        f'<span class="cn-dir">{"← " if arrow_left else ""}{word}{"" if arrow_left else " →"}</span>'
                        f'<span class="cn-title">{html_escape(title)}</span>'
                        + (f'<span class="cn-sub">{html_escape(sub)}</span>' if sub else "") + "</a>\n")

            unit = UNITS.get(ch["slug"].split("-")[0], "chapters")
            block = ("  <!-- chapter-nav -->\n  <nav class=\"chapter-nav\" aria-label=\"Chapter navigation\">\n"
                     + link(i - 1, "prev", True)
                     + f'    <a class="cn-all" href="../">☰ All {unit}</a>\n'
                     + link(i + 1, "next", False)
                     + "  </nav>\n  <!-- /chapter-nav -->\n")
            raw = page.read_bytes()
            crlf = b"\r\n" in raw
            text = raw.decode("utf-8").replace("\r\n", "\n")
            # Always the same shape: "</main>" blank line, nav block, blank line, rest.
            stripped = NAV_RE.sub("", text)
            end = stripped.find("</main>") + len("</main>")
            if end < len("</main>"):
                continue
            new = stripped[:end] + "\n\n" + block + "\n" + stripped[end:].lstrip("\n")
            if new != text:
                page.write_bytes((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))


def verse_index():
    """verses.json for the header's "Go to shloka" menu: every text (texts.json order), its
    chapters (with their description) and each chapter's printed shloka numbers (॥5.13.41॥)."""
    numre = re.compile(r"॥\s*([0-9०-९]+(?:\.[0-9०-९]+)*)\s*॥")

    def numbers(rel):
        page = ROOT / rel / "index.html"
        if not page.exists():
            return None
        html = page.read_text(encoding="utf-8")
        m = re.search(r'<main[^>]*id="content".*?</main>', html, re.S)
        found = numre.findall(m.group(0) if m else html)
        dotted = [n for n in found if "." in n]
        found = dotted or found
        # keep this chapter's own numbers (not verses quoted from elsewhere), in page order
        prefixes = [n.rsplit(".", 1)[0] if "." in n else "" for n in found]
        pre = max(set(prefixes), key=prefixes.count) if prefixes else ""
        seen, tails = set(), []
        for n, p in zip(found, prefixes):
            if p == pre and n not in seen:
                seen.add(n)
                tails.append(n.rsplit(".", 1)[1] if "." in n else n)
        return {"pre": pre + "." if pre else "", "v": tails}

    def chapter(rel, title, subject, group=None):
        nums = numbers(rel)
        if nums is None:
            return None
        c = {"p": rel + "/", "l": title}             # just "Sarga 13" / "Dashaka 24" (names are long)
        if group:
            c["g"] = group
        c.update(nums)
        return c

    out = []
    for e in load_manifest():
        chs = []
        if is_parent(e):
            for w in e.get("works", []):
                g = w.get("title", "").split(" — ")[0]
                chs += [chapter(f"{e['slug']}/{w['slug']}/{c['slug']}", c.get("title", ""), c.get("subject", ""), g)
                        for c in w.get("chapters", [])]
        elif is_work(e):
            chs = [chapter(f"{e['slug']}/{c['slug']}", c.get("title", ""), c.get("subject", ""))
                   for c in e.get("chapters", [])]
        else:
            chs = [chapter(e["slug"], e.get("title", ""), "")]
        chs = [c for c in chs if c]
        if chs:
            out.append({"t": e.get("title", ""), "k": e["slug"], "c": chs})
    (ROOT / "verses.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def stamp_assets():
    """Version-stamp the shared files so browsers fetch new copies as soon as they change
    (GitHub Pages lets browsers reuse cached files for 10 minutes otherwise).

    - script.js's ACCOUNT_JS_VERSION is set to a hash of account.js;
    - every page's style.css / script.js reference gets ?v=<hash of that file>.
    Only files whose text actually changes are rewritten (line endings preserved)."""
    import hashlib

    def short_hash(path):
        return hashlib.sha1(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:10]

    script = ROOT / "script.js"
    raw = script.read_bytes()
    new = re.sub(rb"const ACCOUNT_JS_VERSION = '[^']*';",
                 b"const ACCOUNT_JS_VERSION = '" + short_hash(ROOT / "account.js").encode() + b"';", raw)
    new = re.sub(rb"const VERSES_VERSION = '[^']*';",
                 b"const VERSES_VERSION = '" + short_hash(ROOT / "verses.json").encode() + b"';", new)
    if new != raw:
        script.write_bytes(new)

    versions = {name: short_hash(ROOT / name).encode() for name in ("style.css", "script.js")}
    pat = re.compile(rb'((?:href|src)="(?:\.\./)*)(style\.css|script\.js)(?:\?v=[^"]*)?"')
    changed = 0
    for page in ROOT.rglob("*.html"):
        rel = page.relative_to(ROOT).parts
        if rel[0] in (".git", "_unreleased"):
            continue
        data = page.read_bytes()
        out = pat.sub(lambda m: m.group(1) + m.group(2) + b"?v=" + versions[m.group(2).decode()] + b'"', data)
        if out != data:
            page.write_bytes(out)
            changed += 1
    if changed:
        print(f"Version-stamped style.css/script.js on {changed} page(s)")


def tracker_tag():
    """Rows for the owner's study tracker (tracker/): Sundarakanda (with KK 66-67),
    Narayaneeyam, Shrimad Bhagavatam - number, name, shloka count, chapter path."""
    num = re.compile(r"॥\s*\d+(?:\.\d+)*\.(\d+)\s*॥")
    entries = load_manifest()

    def count_shlokas(nums):
        # Shlokas on the page. A full sarga numbers every verse (a missing number or two still
        # means the highest number is the count); a selection (e.g. Yudhdhakanda 101) is counted.
        if not nums:
            return ""
        n, top = len(set(nums)), max(nums)
        return top if top - n <= 2 else n

    def rows(prefix, chapters, label):
        out = []
        for c in chapters:
            page = ROOT / prefix / c["slug"] / "index.html"
            nums = [int(x) for x in num.findall(page.read_text(encoding="utf-8"))] if page.exists() else []
            out.append({"id": f"{prefix}/{c['slug']}", "no": label(c), "name": c.get("subject") or c.get("title", ""),
                        "shlokas": count_shlokas(nums)})
        return out

    def work(parent, slug):
        p = find_entry(entries, parent)
        return find_work_in(p.get("works", []), slug) if p else None

    texts = []
    kk, sk = work("thestoryofhanuman", "kishkindhakanda"), work("thestoryofhanuman", "sundarakanda")
    yk = work("thestoryofhanuman", "yudhdhakanda")
    if sk:
        # key stays "sundarakanda" (saved tracker data uses it); shown as "The Story of Hanuman"
        texts.append({"key": "sundarakanda", "title": "The Story of Hanuman",
                      "rows": (rows("thestoryofhanuman/kishkindhakanda", kk["chapters"], lambda c: f"KK {c['n']}") if kk else [])
                      + rows("thestoryofhanuman/sundarakanda", sk["chapters"], lambda c: f"SK {c['n']}")
                      + (rows("thestoryofhanuman/yudhdhakanda", yk["chapters"], lambda c: f"YK {c['n']}") if yk else [])})
    nar = find_entry(entries, "narayaneeyam")
    if nar:
        texts.append({"key": "narayaneeyam", "title": "Narayaneeyam",
                      "rows": rows("narayaneeyam", nar["chapters"], lambda c: str(c["n"]))})
    b1, b2 = work("shrimad-bhagavatam-canto-10", "book-1"), work("shrimad-bhagavatam-canto-10", "book-2")
    if b1 or b2:
        texts.append({"key": "bhagavatam", "title": "Shrimad Bhagavatam",
                      "rows": (rows("shrimad-bhagavatam-canto-10/book-1", b1["chapters"], lambda c: str(c["n"])) if b1 else [])
                      + (rows("shrimad-bhagavatam-canto-10/book-2", b2["chapters"], lambda c: str(c["n"])) if b2 else [])})
    # Bhagavad Geeta: tracked here only (not on the website, so no links). Names as in the
    # owner's sheet; shloka counts are the standard ones (700 in all).
    geeta = [("Arjuna Vishad Yoga", 47), ("Sankhya Yoga", 72), ("Karma Yoga", 43),
             ("Gnyana Karma Sanyasa Yoga", 42), ("Karma Sanyas Yoga", 29), ("Atma Sanyama Yoga", 47),
             ("Gnyana Vignyana Yoga", 30), ("Akshara Brahma Yoga", 28), ("Raj Vidya Raj Guhya Yoga", 34),
             ("Vibhuti Yoga", 42), ("Vishwarupa Darshana Yoga", 55), ("Bhakti Yoga", 20),
             ("Kshetra Kshetragnya Vibhaga Yoga", 34), ("Guna Traya Vibhaga Yoga", 27),
             ("Purushottama Yoga", 20), ("Daivasura Sampad Vibhaga Yoga", 24),
             ("Shraddha Traya Vibhaga Yoga", 28), ("Moksha Sanyasa Yoga", 78)]
    def geeta_row(i, n, k):
        # cell keys stay "geeta/ch-N"; a chapter that is on the site links to its page
        row = {"id": f"geeta/ch-{i}", "no": str(i), "name": n, "shlokas": k, "nolink": True}
        if (ROOT / "bhagavad-geeta" / f"ch-{i}" / "index.html").exists():
            row.update(nolink=False, href=f"bhagavad-geeta/ch-{i}")
        return row

    texts.append({"key": "geeta", "title": "Bhagavad Geeta",
                  "rows": [geeta_row(i, n, k) for i, (n, k) in enumerate(geeta, 1)]})
    return ('<script type="application/json" id="tracker-data">'
            + json.dumps(texts, ensure_ascii=False, separators=(",", ":")) + "</script>")


def build_static_pages():
    """Reader account page (sign-in / bookmarks / notes, driven by account.js) and the
    privacy policy (body from _privacy_body.html)."""
    # Chapters per text, keyed by folder, for the Account page's "N of TOTAL studied".
    totals, labels = {}, {}
    for top in load_manifest():
        if is_parent(top):
            short = top.get("title", "").split(" — ")[0]          # "Shrimad Bhagavatam"
            for w in top.get("works", []):
                key = f"{top['slug']}/{w['slug']}"
                totals[key] = len(w.get("chapters", []))
                m = re.match(r"Book (\d+)", w.get("title", ""))
                # Say which collection a part belongs to: "Shrimad Bhagavatam Book 1",
                # "The Story of Hanuman — Kishkindhakanda" (not to be confused with the
                # Eclectic Collection's Kishkindhakanda sarga).
                labels[key] = f"{short} Book {m.group(1)}" if m else f"{short} — {w.get('title', '')}"
        elif is_work(top):
            totals[top["slug"]] = len(top.get("chapters", []))
            labels[top["slug"]] = top.get("title", "")
        else:
            totals[top["slug"]] = 1
            labels[top["slug"]] = top.get("title", "")
    totals_tag = ('<script type="application/json" id="text-totals">'
                  + json.dumps(totals, separators=(",", ":")) + "</script>"
                  + '<script type="application/json" id="text-labels">'
                  + json.dumps(labels, ensure_ascii=False, separators=(",", ":")) + "</script>")
    pages = [
        ("account", "Your account", "Bookmarks, progress and private notes",
         "Your account | Samskrita Svadhyaya",
         "Sign in to Samskrita Svadhyaya to keep bookmarks, track your progress and write private notes.",
         '  <main class="account" id="content">\n    <div id="account-app">'
         '<p class="acct-loading">Loading…</p>'
         '<noscript><p>Please turn on JavaScript to sign in.</p></noscript></div>\n    '
         + totals_tag + '\n  </main>\n',
         True),
        ("tracker", "My study tracker", "Cycles of study, chapter by chapter",
         "Study tracker | Samskrita Svadhyaya",
         "Private study tracker.",
         '  <main class="account tracker" id="content">\n    <div id="tracker-app">'
         '<p class="acct-loading">Loading…</p></div>\n    '
         + tracker_tag() + '\n  </main>\n',
         True),
        ("privacy", "Privacy policy", "What we keep when you sign in, and what we never do",
         "Privacy policy | Samskrita Svadhyaya",
         "How Samskrita Svadhyaya handles reader accounts, bookmarks, notes and announcement emails.",
         '  <main class="content static-page" id="content">\n'
         + (ROOT / "_privacy_body.html").read_text(encoding="utf-8").strip()
         + "\n  </main>\n",
         False),
        # From the owner's Drive doc "Disclaimer and Credits" (body in _disclaimer_body.html).
        ("disclaimer", "Disclaimer and Credits", "About this work, and the sources it draws on",
         "Disclaimer and Credits | Samskrita Svadhyaya",
         "About Samskrita Svadhyaya: a self-study of Sanskrit texts — the sources consulted, and "
         "the word-by-word meanings, anvaya and translations as the author's own work.",
         '  <main class="content static-page" id="content">\n'
         + (ROOT / "_disclaimer_body.html").read_text(encoding="utf-8").strip()
         + "\n  </main>\n",
         False),
    ]
    for slug, title, subtitle, html_title, desc, main_html, noindex in pages:
        html = render_chrome(html_title, desc, "../", fill(STATIC_HERO, TITLE=title, SUBTITLE=subtitle), main_html)
        head = f'  <link rel="canonical" href="https://samskritasvadhyaya.github.io/SamskritaSvadhyaya/{slug}/" />\n'
        if noindex:
            head += '  <meta name="robots" content="noindex" />\n'
        html = html.replace("</head>", head + "</head>", 1)
        out = ROOT / slug / "index.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("page")
    p.add_argument("--slug", required=True)
    p.add_argument("--work", default=None)
    p.add_argument("--parent", default=None)
    p.add_argument("--title", required=True)
    p.add_argument("--title-sa", required=True, dest="title_sa")
    p.add_argument("--subtitle", default="")
    p.add_argument("--subject", default=None, help="chapter description (e.g. a dashaka's name)")
    p.add_argument("--n", type=int, default=None)
    p.add_argument("--body", required=True)
    p.set_defaults(func=build_page)

    w = sub.add_parser("set-work")
    w.add_argument("--slug", required=True)
    w.add_argument("--parent", default=None)
    w.add_argument("--title", required=True)
    w.add_argument("--title-sa", required=True, dest="title_sa")
    w.add_argument("--subtitle", default="")
    w.add_argument("--note", default=None, help="path to an HTML body to embed as preamble")
    w.set_defaults(func=set_work)

    sp = sub.add_parser("set-parent")
    sp.add_argument("--slug", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--title-sa", required=True, dest="title_sa")
    sp.add_argument("--subtitle", default="")
    sp.add_argument("--note", default=None, help="path to an HTML body to embed as preamble")
    sp.set_defaults(func=set_parent)

    wi = sub.add_parser("work-index")
    wi.add_argument("--slug", required=True)
    wi.add_argument("--parent", default=None)
    wi.set_defaults(func=build_work_index)

    pi = sub.add_parser("parent-index")
    pi.add_argument("--slug", required=True)
    pi.set_defaults(func=build_parent_index)

    h = sub.add_parser("home")
    h.set_defaults(func=build_home)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
