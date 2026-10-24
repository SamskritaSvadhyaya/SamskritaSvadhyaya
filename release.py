#!/usr/bin/env python3
"""Stage a work's chapters for gradual (e.g. weekly) release.

Unreleased chapters live in _unreleased/<work>/ (gitignored), together with their
texts.json entries in _unreleased/<work>.json. GitHub Pages publishes every file
in the repo, so withheld pages must be moved out of it entirely, not just unlinked.

Commands:

  release.py hold <work> --after <n>
      Withhold every chapter numbered above <n>.

  release.py next <work> [--count 10]
      Publish the next <count> withheld chapters (lowest numbers first), then
      rebuild the work index and home page.

  release.py status <work>
      Show what is live and what is still withheld.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "texts.json"
HOLD = ROOT / "_unreleased"


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_work(entries, slug):
    for e in entries:
        if e.get("slug") == slug and e.get("type") == "work":
            return e
    raise SystemExit(f"No top-level work '{slug}' in texts.json.")


def rebuild(work):
    for cmd in (["work-index", "--slug", work], ["home"]):
        subprocess.run([sys.executable, str(ROOT / "build.py"), *cmd], check=True)


def hold(args):
    entries = load(MANIFEST, [])
    work = find_work(entries, args.work)
    held_file = HOLD / f"{args.work}.json"
    held = load(held_file, [])
    keep = [c for c in work["chapters"] if c["n"] <= args.after]
    move = [c for c in work["chapters"] if c["n"] > args.after]
    (HOLD / args.work).mkdir(parents=True, exist_ok=True)
    for c in move:
        shutil.move(str(ROOT / args.work / c["slug"]), str(HOLD / args.work / c["slug"]))
    work["chapters"] = keep
    save(MANIFEST, entries)
    save(held_file, sorted(held + move, key=lambda c: c["n"]))
    print(f"{args.work}: withheld {len(move)} chapter(s); {len(keep)} live")
    rebuild(args.work)


def release_next(args):
    entries = load(MANIFEST, [])
    work = find_work(entries, args.work)
    held_file = HOLD / f"{args.work}.json"
    held = sorted(load(held_file, []), key=lambda c: c["n"])
    if not held:
        raise SystemExit(f"{args.work}: nothing left to release.")
    batch, rest = held[:args.count], held[args.count:]
    for c in batch:
        shutil.move(str(HOLD / args.work / c["slug"]), str(ROOT / args.work / c["slug"]))
    work["chapters"] = sorted(work["chapters"] + batch, key=lambda c: c["n"])
    save(MANIFEST, entries)
    save(held_file, rest)
    print(f"{args.work}: released {batch[0]['n']}–{batch[-1]['n']}; "
          f"{len(work['chapters'])} live, {len(rest)} withheld")
    rebuild(args.work)


def status(args):
    work = find_work(load(MANIFEST, []), args.work)
    held = load(HOLD / f"{args.work}.json", [])
    live = [c["n"] for c in work["chapters"]]
    print(f"live: {len(live)} ({min(live)}–{max(live)})" if live else "live: 0")
    print(f"withheld: {len(held)}" + (f" (next: {held[0]['n']})" if held else ""))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hold"); h.add_argument("work"); h.add_argument("--after", type=int, required=True)
    h.set_defaults(func=hold)
    n = sub.add_parser("next"); n.add_argument("work"); n.add_argument("--count", type=int, default=10)
    n.set_defaults(func=release_next)
    s = sub.add_parser("status"); s.add_argument("work")
    s.set_defaults(func=status)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
