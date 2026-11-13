#!/usr/bin/env python3
"""Which pages are behind their Google Doc?  ("update everything")

Every chapter in texts.json records its Google Doc ("doc") and when the page was last made
from it ("synced", UTC). Give this script a listing of the docs with their modifiedTime, as
JSON - either a list of {id, title, modifiedTime} or {group: [ ... ]} - and it prints the
pages whose doc was edited after they were last updated, oldest first.

    python sync-status.py <listing.json>

Then re-import each one (import-drive.py for most texts; see CLAUDE.md for the others).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def pages():
    for e in json.loads((ROOT / "texts.json").read_text(encoding="utf-8")):
        if e.get("works"):
            for w in e["works"]:
                for c in w.get("chapters", []):
                    yield f"{e['slug']}/{w['slug']}/{c['slug']}", c
        elif "chapters" in e:
            for c in e["chapters"]:
                yield f"{e['slug']}/{c['slug']}", c
        else:
            yield e["slug"], e


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    docs = data if isinstance(data, list) else [d for group in data.values() for d in group]
    mod = {d["id"]: (d.get("modifiedTime", "")[:19] + "Z", d.get("title", "")) for d in docs}
    behind, linked = [], set()
    for path, entry in pages():
        doc = entry.get("doc")
        if not doc:
            continue
        linked.add(doc)
        if doc in mod and mod[doc][0] > entry.get("synced", ""):
            behind.append((mod[doc][0], path, mod[doc][1]))
    for when, path, title in sorted(behind):
        print(f"{when}  {path}   <- {title}")
    print(f"{len(behind)} page(s) behind their doc.")
    new = [t for i, (_, t) in mod.items() if i not in linked]
    if new:
        print("Docs in the listing that are not on the site (not imported):", "; ".join(sorted(new)))


if __name__ == "__main__":
    main()
