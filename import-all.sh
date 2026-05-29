#!/usr/bin/env bash
# Batch-import every Bhagavatam chapter download found in a tool-results directory.
#
# Scans <dir> for Google-Drive download JSONs (docx exports whose title looks like
# "...Ch.N"), imports each as chapter ch-N under <work-slug>, then rebuilds the
# work index and the home page.
#
# Usage:
#   ./import-all.sh <tool-results-dir> <work-slug> [max-chapter]

set -euo pipefail

dir="$1"; work="$2"; maxn="${3:-9999}"
here="$(cd "$(dirname "$0")" && pwd)"
want_mime="text/html"   # prefer the color-preserving HTML export

shopt -s nullglob
# Newest files first, so the latest download of a chapter wins on duplicates.
declare -A seen
count=0
for f in $(ls -t "$dir"/*download_file_content*.txt 2>/dev/null); do
  mime="$(jq -r '.mimeType // empty' "$f" 2>/dev/null || true)"
  [ "$mime" = "$want_mime" ] || continue
  title="$(jq -r '.title // empty' "$f" 2>/dev/null || true)"
  case "$title" in *[Cc]h*) : ;; *) continue ;; esac   # only chapter docs
  n="$(printf '%s' "$title" | grep -oE '[0-9]+' | head -1 || true)"
  [ -n "$n" ] || continue
  [ "$n" -le "$maxn" ] || continue
  [ -z "${seen[$n]:-}" ] || continue   # first (newest) file wins if duplicated
  seen[$n]=1
  "$here/import-chapter.sh" "$f" "$work" "ch-$n" "$n"
  count=$((count + 1))
done

echo "Imported $count chapter(s); rebuilding index + home"
python3 "$here/build.py" work-index --slug "$work"
python3 "$here/build.py" home
