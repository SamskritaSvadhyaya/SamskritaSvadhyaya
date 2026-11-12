#!/usr/bin/env python3
"""Re-import one chapter from a Google-Drive download and rebuild the site.

Takes a saved `download_file_content` result (HTML export, JSON with
title/mimeType/content) and works out where it goes from the document's title:

    "Dashaka N - <name>"        -> narayaneeyam/dashaka-N/        title "Dashaka N", description <name>
    "Sundarakanda Sarga N"      -> thestoryofhanuman/sundarakanda/sarga-N/
    "KK - Sarga N - [<name>]"   -> thestoryofhanuman/kishkindhakanda/sarga-N/
    "Yudhdhakanda - Sarga N..." -> thestoryofhanuman/yudhdhakanda/sarga-N/

The chapter's name (Narayaneeyam: from the document title) and its description
(the subject line under the heading) are refreshed from the document every time,
so renaming a doc or editing that line updates the site on the next upload. Shlokas
are joined into tight blocks by gdoc_to_body.py. The old page is replaced, then the
work index, collection page, home page, search metadata and sitemap are rebuilt.

A Narayaneeyam dashaka that is still withheld must be released first
(`release.py next narayaneeyam --count 1`).

Usage:
    python3 import-drive.py <download.json> [--dry-run]
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "texts.json"
DEV = str.maketrans("0123456789", "०१२३४५६७८९")

_SB = r"श्रीमद्भागवतमहापुराणम्\s*Ch\.?\s*(\d+)\b.*"
PATTERNS = [
    # (regex on doc title, parent, work, slug prefix, English unit, Sanskrit unit,
    #  name from title?, (lowest, highest) chapter number for this work)
    (r"Dashaka\s+(\d+)\s*-\s*(.+)", None, "narayaneeyam", "dashaka", "Dashaka", "दशकम्", True, (1, 100)),
    (r"Sundarakanda\s+Sarga\s+(\d+)\b.*", "thestoryofhanuman", "sundarakanda", "sarga", "Sarga", "सर्गः", False, (1, 68)),
    (r"KK\s*-\s*Sarga\s+(\d+)\b.*", "thestoryofhanuman", "kishkindhakanda", "sarga", "Sarga", "सर्गः", False, (1, 67)),
    (r"Yudh+akanda\s*-?\s*Sarga\s+(\d+)\b.*", "thestoryofhanuman", "yudhdhakanda", "sarga", "Sarga", "सर्गः", False, (1, 128)),
    # Shrimad Bhagavatam Canto 10 docs: "श्रीमद्भागवतमहापुराणम् Ch.N".
    # Book 1 (पूर्वार्धः) is chapters 1–49, Book 2 (उत्तरार्धः) chapters 50–90.
    (_SB, "shrimad-bhagavatam-canto-10", "book-1", "ch", "Chapter", "अध्यायः", False, (1, 49)),
    (_SB, "shrimad-bhagavatam-canto-10", "book-2", "ch", "Chapter", "अध्यायः", False, (50, 90)),
]


def run(*cmd, quiet=False):
    subprocess.run([sys.executable, "-B", *cmd], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL if quiet else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("download")
    ap.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    args = ap.parse_args()

    doc = json.loads(Path(args.download).read_text(encoding="utf-8"))
    if doc.get("mimeType") != "text/html":
        raise SystemExit("Download must be an HTML export (exportMimeType: text/html).")
    title = doc.get("title", "").replace("﻿", "").strip()

    for pat, parent, work, prefix, unit_en, unit_sa, name_from_title, (lo, hi) in PATTERNS:
        m = re.fullmatch(pat, title)
        if m and lo <= int(m.group(1)) <= hi:
            break
    else:
        raise SystemExit(f"Don't know where '{title}' belongs; add a pattern to import-drive.py.")
    n = int(m.group(1))
    slug = f"{prefix}-{n}"

    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    owner = next(e for e in entries if e["slug"] == (parent or work))
    w = next(x for x in owner["works"] if x["slug"] == work) if parent else owner
    old = next((c for c in w.get("chapters", []) if c["slug"] == slug), None)
    if old is None:
        held = ROOT / "_unreleased" / f"{work}.json"
        if held.exists() and any(c["slug"] == slug for c in json.loads(held.read_text(encoding="utf-8"))):
            raise SystemExit(f"{work}/{slug} is still withheld; run `release.py next {work}` first.")
        if parent is None:
            raise SystemExit(f"{work}/{slug} is not on the site yet.")

    new_title = f"{unit_en} {n}"
    name = m.group(2).strip() if name_from_title else None      # Narayaneeyam: the dashaka's name
    new_title_sa = f"{unit_sa} {str(n).translate(DEV)}"
    page_dir = ROOT / (f"{parent}/" if parent else "") / work / slug
    print(f"{title}  ->  {page_dir.relative_to(ROOT).as_posix()}/")
    if old:
        if name and old.get("subject") != name:
            print(f"  name:        {old.get('subject')!r} -> {name!r}")
        print(f"  description (before): {old.get('subject', '') or '—'}")
    if args.dry_run:
        return

    body = ROOT / ".import-body.html"
    if page_dir.exists():
        shutil.rmtree(page_dir)
    page_dir.mkdir(parents=True)
    with open(body, "w", encoding="utf-8") as fh:
        subprocess.run([sys.executable, "-B", "gdoc_to_body.py", args.download, str(page_dir / "media")],
                       cwd=ROOT, check=True, stdout=fh)
    page = ["page", "--work", work, "--slug", slug, "--n", str(n),
            "--title", new_title, "--title-sa", new_title_sa, "--body", str(body)]
    if name:
        page += ["--subject", name]
    if parent:
        page[1:1] = ["--parent", parent]
    run("build.py", *page, quiet=True)
    body.unlink()

    run("build.py", "work-index", *(["--parent", parent] if parent else []), "--slug", work, quiet=True)
    if parent:
        run("build.py", "parent-index", "--slug", parent, quiet=True)
    run("build.py", "home", quiet=True)

    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    owner = next(e for e in entries if e["slug"] == (parent or work))
    w = next(x for x in owner["works"] if x["slug"] == work) if parent else owner
    c = next(c for c in w["chapters"] if c["slug"] == slug)
    print(f"  description (now):    {c.get('subject', '') or '—'}")
    print(f"  title: {c['title']} / {c['title_sa']}   rebuilt.")


if __name__ == "__main__":
    main()
