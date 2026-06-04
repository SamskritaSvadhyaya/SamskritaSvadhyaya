#!/usr/bin/env bash
# Import all downloaded sargas under the Ramayana parent (ramayana/<kanda>/sarga-N/).
# Scans the tool-results dir, filters by document-title pattern per kanda, and
# calls import-chapter.sh with the parent + work slugs.
#
# Usage:
#   ./import-ramayana.sh <tool-results-dir>

set -euo pipefail
dir="$1"
here="$(cd "$(dirname "$0")" && pwd)"
parent="ramayana"

dev() {
  python3 -c "import sys;print(str(int(sys.argv[1])).translate(str.maketrans('0123456789','०१२३४५६७८९')))" "$1"
}

# Each kanda is (work-slug, title-pattern-to-grep, "Sanskrit Sarga label")
process() {
  local work="$1" pattern="$2"
  local count=0
  declare -A seen
  shopt -s nullglob
  for f in $(ls -t "$dir"/*download_file_content*.txt); do
    mt=$(jq -r '.mimeType//empty' "$f" 2>/dev/null || true)
    [ "$mt" = "text/html" ] || continue
    ti=$(jq -r '.title//empty' "$f" 2>/dev/null || true)
    case "$ti" in
      *"$pattern"*) ;;
      *) continue ;;
    esac
    n=$(printf '%s' "$ti" | grep -oE '[0-9]+' | head -1 || true)
    [ -n "$n" ] || continue
    [ -z "${seen[$n]:-}" ] || continue
    seen[$n]=1
    "$here/import-chapter.sh" "$f" "$work" "sarga-$n" "$n" "Sarga $n" "सर्गः $(dev "$n")" "$parent"
    count=$((count + 1))
  done
  echo "  $work: imported $count"
}

echo "== Kishkindhakanda =="
process "kishkindhakanda" "KK - Sarga"

echo "== Sundarakanda =="
process "sundarakanda" "Sundarakanda Sarga"

echo "== Yudhdhakanda =="
process "yudhdhakanda" "Yudhdhakanda - Sarga"

echo "Rebuilding work indexes + parent landing + home"
python3 "$here/build.py" work-index --parent "$parent" --slug kishkindhakanda
python3 "$here/build.py" work-index --parent "$parent" --slug sundarakanda
python3 "$here/build.py" work-index --parent "$parent" --slug yudhdhakanda
python3 "$here/build.py" parent-index --slug "$parent"
python3 "$here/build.py" home
