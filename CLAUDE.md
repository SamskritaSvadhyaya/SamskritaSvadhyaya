# Samskrita Svadhyaya

Static site of Sanskrit texts, published with GitHub Pages.

- Repo: https://github.com/SamskritaSvadhyaya/SamskritaSvadhyaya (PUBLIC), branch `main`
- Live: https://samskritasvadhyaya.github.io/SamskritaSvadhyaya/
- Source material: Google Docs in the user's Google Drive (via the claude.ai Google Drive
  connector — needs `/login` with the claude.ai account; it does not load through the AMD gateway).

## Rules

- **No Claude attribution** in commits or PRs: no `Co-Authored-By: Claude` trailer, no
  "Generated with Claude Code" footer. The user has explicitly corrected this ("No co author").
- Push with `env -u GITHUB_TOKEN git push` (and `env -u GITHUB_TOKEN gh ...` for gh).
- Check `git status` before committing; descriptive commit messages.
- **Shlokas are tight couplets/blocks**: each shloka's lines go in one centred `<p>` joined
  with `<br>` (no paragraph gap between its lines). `gdoc_to_body.py` does this on every
  Drive import (`join_dhyana` → `join_verses`). For any other source (.docx via pandoc or a
  hand converter), run the body through `gdoc_to_body.join_dhyana()` before `build.py page`.
  It is safe to re-run on existing pages; text must be unchanged apart from `<p>`/`<br>`.

## Layout

- `texts.json` — manifest. Top-level entries: `raghuvamsha` (work), `ganapati-atharvashirsha`
  (text), `thestoryofhanuman` (parent: Kishkindhakanda/Sundarakanda/Yudhdhakanda sargas),
  `shrimad-bhagavatam-canto-10` (parent: `book-1` पूर्वार्धः ch-1–49, `book-2` उत्तरार्धः
  ch-50–90; Drive folders "Book1 - …" / "Book2 - …" under "Shrimad Bhagavatam Canto 10", docs
  "श्रीमद्भागवतमहापुराणम् Ch.N"), `narayaneeyam` (work), `eclectic-collection` (work).
- `ramayana/` — redirect-only stubs (one per page) sending old `/ramayana/...` links to
  `/thestoryofhanuman/...` (renamed 2026-11-01). Not built by `build.py`; if pages are added under
  `thestoryofhanuman/`, no stub is needed.
- `build.py` — `page`, `set-work` (`--note file.html` adds a preamble), `set-parent`,
  `work-index`, `parent-index`, `home`.
- **`import-drive.py <download.json>`** — the standard way to (re-)upload one chapter from Drive:
  works out the target from the doc title (Dashaka N / Sundarakanda Sarga N / KK - Sarga N /
  Yudhdhakanda - Sarga N), replaces the old page, refreshes the name (Narayaneeyam: the dashaka name from the doc
  title, shown under the "Dashaka N" heading) and description from the doc, rebuilds indexes, home, SEO and sitemap. `--dry-run` shows
  what would change. Refuses withheld dashakas (release first) and unknown docs. Keep scratch
  files (diffs, staging) OUT of the repo — `*.diff` is gitignored after strays got published.
- Shri Ganapati Atharvashirsha (standalone text, not handled by import-drive.py): Drive doc
  "Shri Ganapati Atharvashirsha" in folder "Shri Ganapati Collection". Update with
  `gdoc_to_body.py <json> <tmp-media>` then `build.py page --slug ganapati-atharvashirsha --title
  "Shri Ganapati Atharvashirsha" --title-sa "श्री गणपतिः अथर्वशीर्षः" --subtitle "" --body <file>`, then `build.py home`.
- Drive downloads sometimes arrive as a raw .html file instead of the usual JSON: wrap it as
  {"content": base64(html), "mimeType": "text/html", "title": "<doc title>"} before importing.
- `gdoc_to_body.py` — converts a Drive `download_file_content` (text/html export) result JSON
  into a page body, keeping colours, alignment, sizes.
- **No doc page headers/footers on the site**: gdoc_to_body.py skips Google's header/footer
  (the `<div>`s directly under `<body>` in the HTML export); they stay in the docs.
- **Plain English spelling, no diacritics** (owner's style): `plain_english.py` turns IAST letters into
  plain spelling (Raghuvaṃśa → Raghuvamsha, Kālidāsa → Kalidasa, Śrīla → Shrila; ś/ṣ → sh, ṛ → ri).
  gdoc_to_body.py applies it to every upload; `python plain_english.py` fixes the whole site.
- **No pictures anywhere on the site** (owner's decision 2026-11-09): `gdoc_to_body.py` drops every
  picture in a doc (`KEEP_IMAGES = False`), texts.json has no `image` fields, home/collection tiles
  show ॐ. If a doc has a picture that is really part of a sentence (e.g. a number pasted as an
  image), type it into the page as text. The only image file is `og-image.png` (ॐ link preview
  used by every page via seo.py — not shown on the site).
- `import-chapter.sh`, `import-all.sh`, `import-ramayana.sh`, `convert.sh` — importers.
- `import-narayaneeyam.sh <download-dir>` — imports all 100 dashakas. Re-running it republishes
  all 100 — run `release.py hold narayaneeyam --after <n>` afterwards.
- Previous / Next buttons at the bottom of every chapter page: `build.py home` (`chapter_nav`)
  rewrites a `<!-- chapter-nav -->` block after `</main>` on each chapter, in texts.json order,
  running on across a parent's works (Kishkindhakanda → Sundarakanda → Yudhdhakanda; Book 1 →
  Book 2). Automatic for new/re-imported chapters; stable on re-runs.
  script.js builds from that block: fixed side arrows ‹ › (screens ≥1000px, hover label), a
  ‹ Previous · All · Next › row under the heading (narrower screens), and the ← / → keys.
- Chapter descriptions: `build.py page` reads each chapter's subject line from its doc (the
  English line under the "Sundarakanda Sarga N" heading, e.g. "Hanuman crosses the ocean,
  reaches Lanka"), stores it as the chapter's `subject` in texts.json, and shows it under the
  page title and on the chapter card — always IN FULL (the user wants complete descriptions;
  never shorten them). A heading typed over two lines in the doc is joined. Narayaneeyam dashakas are titled
  "Dashaka N" with the doc title's name as the subject (import-drive passes `--subject`). Editing the line in the doc + re-importing updates it.
- `seo.py` — search metadata: descriptive `<title>`/description (work, chapter no., subject line
  from the page, Sanskrit name), canonical URL and link-preview tags in a `<!-- seo -->` block,
  plus `sitemap.xml` of all published pages. Runs automatically at the end of `build.py home`
  (so every build/release keeps it current); safe to run by hand. Sitemap URL for Google
  Search Console: https://samskritasvadhyaya.github.io/SamskritaSvadhyaya/sitemap.xml
- `googleeeb64c879486498d.html` — Google Search Console ownership file (property: URL prefix
  https://samskritasvadhyaya.github.io/SamskritaSvadhyaya/). Never delete or edit it; Google
  re-checks it periodically.
- Downloading many Drive docs in parallel: tool-result files finishing in the same millisecond
  overwrite each other — copy each result out right after download and verify none is missing.

## Disclaimer and Credits

`disclaimer/` page, built by `build.py home` (`build_static_pages`) from `_disclaimer_body.html`,
which reproduces the owner's Drive doc "Disclaimer and Credits" (id
`1biGLjg1QIBtBIhn-Y9okwwvoSImMBaP8EFWUU8F4Hf8`) word for word. script.js adds the
"Disclaimer and Credits" link to every page's footer line. To update: re-read the doc,
rewrite `_disclaimer_body.html`, `python build.py home`.

## Reader accounts (optional sign-in)

Reading stays open to everyone; signing in adds bookmarks, "studied" marks, continue-reading and
private notes, plus an announcements opt-in. Firebase project `samskrita-svadhyaya` (owner's Google
account; Authentication: Email/Password + Google; Firestore, lite SDK 11.10.0 from gstatic).

- `account.js` — all Firebase code (config values are public by design). `script.js` adds the
  "Sign in"/"Account" header link, the bar above chapter text and the footer Privacy link on every
  page, and imports `account.js` only on `account/` or when localStorage `ss-signed-in` is set.
- `account/` and `privacy/` pages are generated by `build.py home` (`build_static_pages`); privacy
  text is `_privacy_body.html` (update its date when edited).
- Data: `users/{uid}` (profile, `lastPage`), `users/{uid}/pages/{path with / -> |}`
  (bookmarked/studied/note, plus `verses: {n: {t: first 40 chars of the shloka, note}}` — per-shloka
  notes, matched back by `t` (opening words), then `num` (printed shloka number), then position —
  so notes/ribbons follow shlokas that are moved or reworded on re-import, and are re-filed under
  the new position (verses map rewritten with updateDoc, so no duplicates); a shloka = centred Devanagari block followed by a
  left-aligned meaning paragraph; `mark: {n, t}` = the shloka the reader ribboned as "I stopped
  here" + `markAt`, also copied into `lastPage.mark`; home + Account list the latest mark per
  top-level text ("Where I stopped", links `#mark`)), `subscribers/{uid}` (announcements list;
  the site owner gets a CSV download button on the Account page).
- Progress box shows only bars per text ("N of TOTAL studied" / "completed"); the earlier
  reading-cycles and past-readings features were removed at the owner's request (Nov 2026).
  Page docs are near the rules' 12-field limit (11 used) — raise it in firestore.rules first.
- Notes are formatted (bold / italics / underline / highlight): account.js `noteEditor` (toolbar +
  contenteditable), stored as `<!--rich-->` + HTML cleaned by `cleanNote` (only b, i, u, mark, br);
  older plain-text notes still display/edit (no marker). Paste is plain text only.
- Cache-busting: `build.py home` (`stamp_assets`) adds `?v=<content hash>` to every page's
  style.css / script.js link and sets script.js's `ACCOUNT_JS_VERSION` from account.js's hash —
  so after editing any of those three files, run `python build.py home` before committing.
- Security rules: `firestore.rules` (gitignored — names the owner's email); paste into Firebase
  console → Firestore → Rules → Publish after any change.

## Weekly release (Narayaneeyam)

The user releases **10 dashakas per week**. Withheld chapters live in `_unreleased/`
(gitignored, NOT in the repo — must be copied between machines by hand).

```
./release.py status narayaneeyam
./release.py next narayaneeyam          # moves next 10 in, rebuilds index + home
git add narayaneeyam texts.json index.html
git commit -m "Release Narayaneeyam dashakas X-Y"
env -u GITHUB_TOKEN git push
```

Then verify the Pages deploy (`env -u GITHUB_TOKEN gh run list -L 1`) and that the last
released dashaka returns 200 and the next one 404.

History: 1–10 live 2026-10-22; 11–20 released 2026-11-01, then 16–20 withheld again the same
day; 16–17 re-released 2026-11-01, 18 on 11-01, 19 on 11-02, 20 on 11-03; **21–100 all released
2026-11-04** (from their Drive docs). All 100 are live; `_unreleased/narayaneeyam/` is empty, so
the weekly-release steps above no longer apply — update a dashaka with `import-drive.py`.
Lately the user releases one or two at a time, each from its latest Drive revision: after
`release.py next`, rebuild the page from the downloaded Drive doc (gdoc_to_body + build.py page
with the manifest's title), then `work-index`, `home`.

## Windows (PowerShell)

The commands above are for Linux/bash. On Windows:

- Run scripts with `python`, not `./`: `python release.py status narayaneeyam`,
  `python release.py next narayaneeyam`, `python build.py home`.
- Push with plain `git push` (GitHub sign-in via `gh auth login` + `gh auth setup-git`).
  If `GITHUB_TOKEN` is ever set, clear it first: `Remove-Item Env:GITHUB_TOKEN`.
- The `.sh` importers need Git Bash (`C:\Program Files\Git\bin\bash.exe`).
- Saved permissions in `.claude/settings.local.json` are bash patterns and won't match
  PowerShell commands.

Note: all 100 dashakas are still visible in git history (commit `8177731`) since the repo is
public; the user has not asked to rewrite history.
