#!/usr/bin/env python3
"""Static-site generator for the Samskrita Svadhyaya text library.

Two commands:

  build.py page --slug <slug> --title <t> --title-sa <sa> --subtitle <s> --body <file.html>
      Wrap a pandoc HTML body in the site template and write <slug>/index.html,
      then add/update the entry in texts.json.

  build.py home
      Regenerate the root index.html (card grid) from texts.json.

Normally invoked through convert.sh, not by hand.
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

# {{REL}} is the relative path back to site root ("" for home, "../" for a text page).
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

PAGE_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{{TITLE}} — {{TITLE_SA}}</title>
  <meta name="description" content="{{TITLE}} — Sanskrit verses with word-by-word meanings, anvaya, literal translation, and simple meaning." />
  <link rel="icon" href=\"""" + FAVICON + """\" />
  <link rel="stylesheet" href="{{REL}}style.css" />
</head>
<body>
""" + HEADER + """
  <section class="hero">
    <div class="om-large">ॐ</div>
    <h1>{{TITLE}}</h1>
    <p class="subtitle">{{TITLE_SA}}{{SUBSEP}}{{SUBTITLE}}</p>
    <div class="divider"><span class="om">ॐ</span></div>
  </section>

  <main class="content" id="content">
"""

PAGE_TAIL = "  </main>\n" + FOOTER

HOME_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Samskrita Svadhyaya — Sanskrit Text Library</title>
  <meta name="description" content="A self-study library of Sanskrit texts: verses with word-by-word meaning, anvaya, and translation." />
  <link rel="icon" href=\"""" + FAVICON + """\" />
  <link rel="stylesheet" href="style.css" />
</head>
<body>
""" + HEADER.replace("{{REL}}", "") + """
  <section class="hero">
    <div class="om-large">ॐ</div>
    <h1>Samskrita Svadhyaya</h1>
    <p class="subtitle">A self-study library of Sanskrit texts — verses with meaning, anvaya, and translation</p>
    <div class="divider"><span class="om">ॐ</span></div>
  </section>

  <main class="home">
    <div class="home-grid">
{{CARDS}}
    </div>
  </main>
""" + FOOTER.replace("{{REL}}", "")

CARD = """      <a class="text-card" href="{slug}/">
        <div class="card-emblem">{emblem}</div>
        <div class="card-body">
          <span class="card-title-sa" lang="sa">{title_sa}</span>
          <span class="card-title">{title}</span>
          <span class="card-sub">{subtitle}</span>
        </div>
      </a>"""

EMPTY_CARD = """      <div class="text-card empty">
        <div class="card-emblem">ॐ</div>
        <div class="card-body">
          <span class="card-title">More texts coming soon</span>
        </div>
      </div>"""


def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return []


def save_manifest(entries):
    MANIFEST.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def clean_body(body, slug):
    # Media was extracted to <slug>/media/; the page lives at <slug>/index.html,
    # so rewrite the image src (which may carry an absolute or relative prefix)
    # to be relative to the page.
    body = re.sub(rf'src="[^"]*?{re.escape(slug + "/media/")}', 'src="media/', body)
    # Drop pandoc's inline width/height (the stylesheet controls image sizing).
    body = re.sub(r'\s*style="width:[^"]*"', "", body)
    return body


def first_image(body, slug):
    m = re.search(r'src="(?:\./)?media/([^"]+)"', body)
    return f"{slug}/media/{m.group(1)}" if m else None


def fill(template, **kw):
    out = template
    for key, val in kw.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def build_page(args):
    body = Path(args.body).read_text(encoding="utf-8")
    body = clean_body(body, args.slug)
    image = first_image(body, args.slug)

    subtitle = args.subtitle or ""
    head = fill(
        PAGE_HEAD,
        REL="../",
        TITLE=args.title,
        TITLE_SA=args.title_sa,
        SUBTITLE=subtitle,
        SUBSEP=" · " if subtitle else "",
    )
    tail = fill(PAGE_TAIL, REL="../")

    out_dir = ROOT / args.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(head + body + tail, encoding="utf-8")

    entries = [e for e in load_manifest() if e.get("slug") != args.slug]
    entries.append(
        {
            "slug": args.slug,
            "title": args.title,
            "title_sa": args.title_sa,
            "subtitle": subtitle,
            "image": image,
        }
    )
    entries.sort(key=lambda e: e["title"].lower())
    save_manifest(entries)
    print(f"Wrote {args.slug}/index.html and updated texts.json")


def build_home(_args=None):
    entries = load_manifest()
    if entries:
        cards = "\n".join(
            CARD.format(
                slug=e["slug"],
                title=e["title"],
                title_sa=e.get("title_sa", ""),
                subtitle=e.get("subtitle", ""),
                emblem=(
                    f'<img src="{e["image"]}" alt="" loading="lazy" />'
                    if e.get("image")
                    else "ॐ"
                ),
            )
            for e in entries
        )
    else:
        cards = EMPTY_CARD
    (ROOT / "index.html").write_text(HOME_HEAD.replace("{{CARDS}}", cards), encoding="utf-8")
    print(f"Wrote index.html (home) with {len(entries)} text(s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("page", help="generate a text page")
    p.add_argument("--slug", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--title-sa", required=True, dest="title_sa")
    p.add_argument("--subtitle", default="")
    p.add_argument("--body", required=True)
    p.set_defaults(func=build_page)

    h = sub.add_parser("home", help="regenerate the home page")
    h.set_defaults(func=build_home)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
