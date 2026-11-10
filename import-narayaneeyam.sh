#!/usr/bin/env bash
# Import all downloaded Narayaneeyam dashakas as narayaneeyam/dashaka-N/.
# Scans a directory of Google-Drive download JSONs (HTML exports titled
# "Dashaka N - <subject>"), imports each with the subject as its English title,
# collapses the images repeated across dashakas, then rebuilds the index + home.
#
# Usage:
#   ./import-narayaneeyam.sh <download-dir>

set -euo pipefail
dir="$1"
here="$(cd "$(dirname "$0")" && pwd)"
work="narayaneeyam"

dev() {
  python3 -c "import sys;print(str(int(sys.argv[1])).translate(str.maketrans('0123456789','०१२३४५६७८९')))" "$1"
}

python3 "$here/build.py" set-work --slug "$work" --title "Narayaneeyam" --title-sa "नारायणीयम्" \
  --subtitle "Melpathur Narayana Bhattathiri · 100 dashakas" --note "$here/narayaneeyam-note.html"

declare -A seen
count=0
shopt -s nullglob
for f in $(ls -t "$dir"/*.json "$dir"/*download_file_content*.txt 2>/dev/null); do
  [ "$(jq -r '.mimeType//empty' "$f" 2>/dev/null || true)" = "text/html" ] || continue
  ti="$(jq -r '.title//empty' "$f" 2>/dev/null || true)"
  case "$ti" in Dashaka*) ;; *) continue ;; esac
  n="$(printf '%s' "$ti" | grep -oE '[0-9]+' | head -1)"
  [ -z "${seen[$n]:-}" ] || continue
  seen[$n]=1
  subject="$(printf '%s' "$ti" | sed -E 's/^Dashaka[[:space:]]*[0-9]+[[:space:]]*-[[:space:]]*//; s/[[:space:]]+$//')"
  "$here/import-chapter.sh" "$f" "$work" "dashaka-$n" "$n" "$subject" "दशकम् $(dev "$n")"
  count=$((count + 1))
done
echo "Imported $count dashaka(s)"

python3 "$here/build.py" work-index --slug "$work"
python3 "$here/build.py" home
