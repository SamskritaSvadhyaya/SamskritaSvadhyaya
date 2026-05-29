#!/usr/bin/env python3
"""Static-site generator for the Samskrita Svadhyaya text library.

The library (texts.json) holds two kinds of top-level entries:

  - "text": a standalone text -> /<slug>/index.html
  - "work": a multi-chapter work -> /<slug>/index.html (chapter index)
            with chapters at /<slug>/<ch-slug>/index.html

Commands:

  build.py page --slug <s> [--work <w>] --title <t> --title-sa <sa>
                [--subtitle <s>] [--n <int>] --body <file.html>
      Wrap a pandoc HTML body in the site template. With --work, the page is a
      chapter under that work; without, it's a standalone text. Updates texts.json.

  build.py set-work --slug <s> --title <t> --title-sa <sa> [--subtitle <s>]
      Create/update a work entry (preserving its chapters).

  build.py work-index --slug <s>
      Regenerate <slug>/index.html (the chapter index) for a work.

  build.py home
      Regenerate the root index.html (top-level card grid).

Normally driven by convert.sh, not run by hand.
"""

import argparse
import json
import re
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


def is_work(entry):
    return entry.get("type") == "work" or "chapters" in entry


def clean_body(body):
    # Extracted media always lands in <page-dir>/media/; rewrite any absolute or
    # nested src down to a path relative to the page.
    body = re.sub(r'src="[^"]*?/media/', 'src="media/', body)
    # Drop pandoc's inline width/height (the stylesheet controls image sizing).
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


def build_page(args):
    body = clean_body(Path(args.body).read_text(encoding="utf-8"))
    entries = load_manifest()

    if args.work:
        rel = "../../"
        page_dir = ROOT / args.work / args.slug
        rel_from_root = f"{args.work}/{args.slug}"
        work = find_entry(entries, args.work)
        if work is None or not is_work(work):
            raise SystemExit(f"Run set-work for '{args.work}' before adding chapters.")
        crumb = (
            f'    <a class="crumb" href="../">↩ {work["title"]}</a>\n'
        )
    else:
        rel = "../"
        page_dir = ROOT / args.slug
        rel_from_root = args.slug
        crumb = ""

    image = first_image(body, rel_from_root)
    subtitle = args.subtitle or ""

    html = (
        fill(DOC_OPEN, REL=rel,
             HTML_TITLE=f"{args.title} — {args.title_sa}",
             DESC=f"{args.title} — Sanskrit text with word-by-word meaning, anvaya, and translation.")
        + HEADER.replace("{{REL}}", rel)
        + fill(PAGE_HERO,
               BREADCRUMB=crumb,
               TITLE=args.title,
               TITLE_SA=args.title_sa,
               SUBTITLE=subtitle,
               SUBSEP=" · " if subtitle else "")
        + body
        + "  </main>\n"
        + FOOTER.replace("{{REL}}", rel)
    )

    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "index.html").write_text(html, encoding="utf-8")

    if args.work:
        chapters = [c for c in work.get("chapters", []) if c.get("slug") != args.slug]
        chapters.append({
            "slug": args.slug,
            "title": args.title,
            "title_sa": args.title_sa,
            "n": args.n if args.n is not None else len(chapters) + 1,
            "image": image,
        })
        chapters.sort(key=lambda c: c.get("n", 0))
        work["chapters"] = chapters
    else:
        entries = [e for e in entries if e.get("slug") != args.slug]
        entries.append({
            "type": "text",
            "slug": args.slug,
            "title": args.title,
            "title_sa": args.title_sa,
            "subtitle": subtitle,
            "image": image,
        })
        entries.sort(key=lambda e: e["title"].lower())

    save_manifest(entries)
    print(f"Wrote {rel_from_root}/index.html and updated texts.json")


def set_work(args):
    entries = load_manifest()
    work = find_entry(entries, args.slug)
    if work is None:
        work = {"type": "work", "slug": args.slug, "chapters": []}
        entries.append(work)
    work["type"] = "work"
    work["title"] = args.title
    work["title_sa"] = args.title_sa
    work["subtitle"] = args.subtitle or ""
    work.setdefault("chapters", [])
    save_manifest(entries)
    print(f"Set work '{args.slug}'")


def render_chrome(title, desc, rel, hero, body_main):
    return (
        fill(DOC_OPEN, REL=rel, HTML_TITLE=title, DESC=desc)
        + HEADER.replace("{{REL}}", rel)
        + hero
        + body_main
        + FOOTER.replace("{{REL}}", rel)
    )


def build_work_index(args):
    entries = load_manifest()
    work = find_entry(entries, args.slug)
    if work is None or not is_work(work):
        raise SystemExit(f"No work named '{args.slug}'.")

    chapters = sorted(work.get("chapters", []), key=lambda c: c.get("n", 0))
    cards = "\n".join(
        """      <a class="chapter-card" href="{slug}/">
        <span class="chapter-num">{num}</span>
        <span class="chapter-meta">
          <span class="chapter-title-sa" lang="sa">{title_sa}</span>
          <span class="chapter-title">{title}</span>
        </span>
      </a>""".format(
            slug=c["slug"],
            num=dev_num(c.get("n", 0)),
            title_sa=c.get("title_sa", ""),
            title=c.get("title", ""),
        )
        for c in chapters
    ) or '      <p class="empty-note">No chapters yet.</p>'

    sub = work.get("subtitle", "")
    hero = fill(
        PAGE_HERO.replace('<main class="content" id="content">', '<main class="home">'),
        BREADCRUMB='    <a class="crumb" href="../index.html">↩ All texts</a>\n',
        TITLE=work["title"],
        TITLE_SA=work["title_sa"],
        SUBTITLE=sub,
        SUBSEP=" · " if sub else "",
    )
    body_main = f'    <div class="chapter-grid">\n{cards}\n    </div>\n  </main>\n'

    html = render_chrome(
        f'{work["title"]} — {work["title_sa"]}',
        f'{work["title"]} — chapter index',
        "../",
        hero,
        body_main,
    )
    (ROOT / args.slug / "index.html").write_text(html, encoding="utf-8")
    print(f"Wrote {args.slug}/index.html ({len(chapters)} chapter(s))")


def build_home(_args=None):
    entries = load_manifest()
    cards = []
    for e in entries:
        if is_work(e):
            count = len(e.get("chapters", []))
            sub = e.get("subtitle") or f"{count} chapter{'s' if count != 1 else ''}"
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("page")
    p.add_argument("--slug", required=True)
    p.add_argument("--work", default=None)
    p.add_argument("--title", required=True)
    p.add_argument("--title-sa", required=True, dest="title_sa")
    p.add_argument("--subtitle", default="")
    p.add_argument("--n", type=int, default=None)
    p.add_argument("--body", required=True)
    p.set_defaults(func=build_page)

    w = sub.add_parser("set-work")
    w.add_argument("--slug", required=True)
    w.add_argument("--title", required=True)
    w.add_argument("--title-sa", required=True, dest="title_sa")
    w.add_argument("--subtitle", default="")
    w.set_defaults(func=set_work)

    wi = sub.add_parser("work-index")
    wi.add_argument("--slug", required=True)
    wi.set_defaults(func=build_work_index)

    h = sub.add_parser("home")
    h.set_defaults(func=build_home)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
