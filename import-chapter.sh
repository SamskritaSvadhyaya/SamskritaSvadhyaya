#!/usr/bin/env bash
# Convert a Google-Drive download (saved tool-result JSON) into a styled page and
# update texts.json. Handles both HTML exports (color-preserving, preferred) and
# docx exports (via pandoc).
#
# Usage:
#   ./import-chapter.sh <tool-result.json> <work-slug|-> <slug> <n> ["<Title>"] ["<Title SA>"]
#
# Pass "-" as <work-slug> for a standalone text (page lives at <slug>/ instead of
# <work>/<slug>/). <n> is the chapter number (ignored for standalone texts).

set -euo pipefail

if [ "$#" -lt 4 ]; then
  echo "Usage: $0 <tool-result.json> <work-slug|-> <slug> <n> [\"<Title>\"] [\"<Title SA>\"]" >&2
  exit 1
fi

json="$1"; work="$2"; slug="$3"; n="$4"; title="${5:-}"; title_sa="${6:-}"
here="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$title" ]; then title="Chapter $n"; fi
if [ -z "$title_sa" ]; then
  dev="$(python3 -c "import sys;print(str(int(sys.argv[1])).translate(str.maketrans('0123456789','०१२३४५६७८९')))" "$n")"
  title_sa="अध्यायः $dev"
fi

if [ "$work" = "-" ]; then
  outdir="$slug"
else
  outdir="$work/$slug"
fi
media_dir="$here/$outdir/media"
mkdir -p "$here/$outdir"

mime="$(jq -r '.mimeType // empty' "$json")"
tmp_body="$(mktemp)"
tmp_docx=""
cleanup() { rm -f "$tmp_body" "${tmp_docx:-}"; }
trap cleanup EXIT

case "$mime" in
  text/html)
    python3 "$here/gdoc_to_body.py" "$json" "$media_dir" > "$tmp_body"
    ;;
  *)
    tmp_docx="$(mktemp --suffix=.docx)"
    jq -r '.content' "$json" | base64 -d > "$tmp_docx"
    pandoc "$tmp_docx" -f docx -t html --extract-media="$here/$outdir" -o "$tmp_body"
    ;;
esac

if [ "$work" = "-" ]; then
  python3 "$here/build.py" page --slug "$slug" \
    --title "$title" --title-sa "$title_sa" --body "$tmp_body"
else
  python3 "$here/build.py" page --work "$work" --slug "$slug" --n "$n" \
    --title "$title" --title-sa "$title_sa" --body "$tmp_body"
fi

echo "Imported $outdir"
