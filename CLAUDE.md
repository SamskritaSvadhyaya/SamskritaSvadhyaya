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

## Layout

- `texts.json` — manifest. Top-level entries: `raghuvamsha` (work), `ganapati-atharvashirsha`
  (text), `ramayana` (parent), `shrimad-bhagavatam-canto-10` (parent), `narayaneeyam` (work).
- `build.py` — `page`, `set-work` (`--note file.html` adds a preamble), `set-parent`,
  `work-index`, `parent-index`, `home`.
- `gdoc_to_body.py` — converts a Drive `download_file_content` (text/html export) result JSON
  into a page body, keeping colours, alignment, sizes.
- `import-chapter.sh`, `import-all.sh`, `import-ramayana.sh`, `convert.sh` — importers.
- `import-narayaneeyam.sh <download-dir>` — imports all 100 dashakas, then `dedupe-media.py`.
  Must be run with all 100 downloads at once (dedupe rebuilds `narayaneeyam/media/` from
  scratch). Re-running it republishes all 100 — run `release.py hold narayaneeyam --after <n>`
  afterwards.
- `dedupe-media.py <work>` — collapses repeated chapter images into `<work>/media/<sha1>.<ext>`.
- Downloading many Drive docs in parallel: tool-result files finishing in the same millisecond
  overwrite each other — copy each result out right after download and verify none is missing.

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

History: 1–10 live 2026-10-22; 11–20 released 2026-11-01.

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
