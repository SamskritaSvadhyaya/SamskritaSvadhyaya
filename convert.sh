#!/usr/bin/env bash
# Convert a .docx into a styled text page under <slug>/ and refresh the home page.
#
# Usage:
#   ./convert.sh <file.docx> <slug> "<Title>" "<Devanagari title>" "<subtitle>"
#
# Example:
#   ./convert.sh "Shri Ganapati Atharvashirsha.docx" \
#       ganapati-atharvashirsha \
#       "Shri Ganapati Atharvashirsha" \
#       "श्री गणपति अथर्वशीर्ष" \
#       "with anvaya, word-by-word meaning, and translation"

set -euo pipefail

if [ "$#" -lt 4 ]; then
  echo "Usage: $0 <file.docx> <slug> \"<Title>\" \"<Devanagari title>\" [\"<subtitle>\"]" >&2
  exit 1
fi

docx="$1"
slug="$2"
title="$3"
title_sa="$4"
subtitle="${5:-}"

here="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$docx" ]; then
  echo "Error: docx not found: $docx" >&2
  exit 1
fi

mkdir -p "$here/$slug"
tmp_body="$(mktemp)"
trap 'rm -f "$tmp_body"' EXIT

# Extract embedded media into <slug>/media and emit an HTML body fragment.
pandoc "$docx" -f docx -t html --extract-media="$here/$slug" -o "$tmp_body"

python3 "$here/build.py" page \
  --slug "$slug" \
  --title "$title" \
  --title-sa "$title_sa" \
  --subtitle "$subtitle" \
  --body "$tmp_body"

python3 "$here/build.py" home

echo "Done: $slug/index.html"
