#!/usr/bin/env python3
"""Update the website from Google Drive, with no computer: the "Update website" button on the phone.

Runs on GitHub (.github/workflows/update-website.yml, started from the GitHub app: Actions ->
"Update website" -> Run workflow). It signs in to Google Drive as a service account (key in the
repository secret GDRIVE_SA_KEY; the owner shares her Drive folders with that account, view only),
lists every Google Doc it can see, and re-imports each doc edited since it was last put on the
website - the same steps as the laptop's update-website.py, which it reuses. Docs it does not
recognise (notes, lists...) are skipped. Then `build.py home`; the workflow commits and pushes.

drive-sync.json = {doc id: modifiedTime last handled}. A doc missing from it is judged by the
chapter's `synced` time in texts.json (if it is a chapter's doc), else handled once as new.

    python drive-update.py            # needs GDRIVE_SA_KEY (the service account's JSON key)
    python drive-update.py --dry-run  # only list what would be updated
"""
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "drive-sync.json"
API = "https://www.googleapis.com/drive/v3"
# Website pages that are not chapters (no shlokas, not in texts.json): always handled.
SPECIAL = re.compile(r"(Geeta\s+)?Themes$|Disclaimer\s+and\s+Credits$", re.I)

spec = importlib.util.spec_from_file_location("updater", ROOT / "update-website.py")
uw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uw)


def session():
    info = json.loads(os.environ["GDRIVE_SA_KEY"].lstrip("﻿").strip())
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    creds.refresh(Request())
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + creds.token
    return s, info.get("client_email", "")


def all_docs(s):
    docs, token = [], None
    while True:
        r = s.get(f"{API}/files", params={
            "q": "mimeType='application/vnd.google-apps.document' and trashed=false",
            "fields": "nextPageToken, files(id, name, modifiedTime)", "pageSize": 1000,
            "includeItemsFromAllDrives": "true", "supportsAllDrives": "true",
            **({"pageToken": token} if token else {})})
        r.raise_for_status()
        docs += r.json().get("files", [])
        token = r.json().get("nextPageToken")
        if not token:
            return docs


def chapter_synced():
    """{doc id: synced time} for every page made from a doc (texts.json)."""
    out = {}

    def take(x):
        if x.get("doc") and x.get("synced"):
            out[x["doc"]] = x["synced"]
    for e in json.loads((ROOT / "texts.json").read_text(encoding="utf-8")):
        take(e)
        for w in e.get("works", []):
            for c in w.get("chapters", []):
                take(c)
        for c in e.get("chapters", []):
            take(c)
    return out


def page_docs():
    """{page path: doc id} for every page made from a doc."""
    out = {}
    for e in json.loads((ROOT / "texts.json").read_text(encoding="utf-8")):
        if e.get("doc"):
            out[e["slug"]] = e["doc"]
        for w in e.get("works", []):
            for c in w.get("chapters", []):
                if c.get("doc"):
                    out[f"{e['slug']}/{w['slug']}/{c['slug']}"] = c["doc"]
        for c in e.get("chapters", []):
            if c.get("doc"):
                out[f"{e['slug']}/{c['slug']}"] = c["doc"]
    return out


def norm(t):                    # "2026-11-21T19:07:31.102Z" / "2026-11-21T19:07:31Z" -> comparable
    return (t or "")[:19]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    dry = "--dry-run" in sys.argv
    allow_new = bool(os.environ.get("SS_ALLOW_NEW"))     # workflow tick-box "Also add new chapters"
    if not allow_new:
        uw.ENV["SS_NO_NEW_CHAPTERS"] = "1"                # import-drive.py then refuses new chapters
    s, who = session()
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    synced = chapter_synced()
    docs = all_docs(s)
    print(f"Google Drive ({who}): {len(docs)} docs shared with the website.")
    unseen = set(synced) - {d["id"] for d in docs}
    if unseen:                       # e.g. a doc moved into a folder that is not shared with the robot
        print(f"\nWARNING: {len(unseen)} website page(s) have a doc the button cannot see (moved to a folder not"
              " shared with it?) - they are not updated from the phone:")
        for path, doc in sorted(page_docs().items()):
            if doc in unseen:
                print("   " + path)
    todo = []
    for d in docs:
        seen = state.get(d["id"]) or synced.get(d["id"])
        if not seen or norm(d["modifiedTime"]) > norm(seen):
            todo.append(d)
    todo.sort(key=lambda d: d["modifiedTime"])
    if not todo:
        print("Every page already matches its Google Doc - nothing to update.")
    done, skipped = [], []
    if dry:                                                       # the check: website pages first
        pages = [d for d in todo if d["id"] in synced or SPECIAL.match(d["name"].strip())]
        others = [d for d in todo if d not in pages]
        print("\nWEBSITE PAGES whose doc was edited - these will be updated:")
        for d in pages:
            print(f"   {d['name'].strip()}   (edited {d['modifiedTime'][:10]})")
        if not pages:
            print("   none - every page matches its doc")
        print("\nOther docs edited (not on the website - skipped; a new chapter is added only with"
              " 'Also add new chapters' ticked and only if it has shlokas):")
        print("   " + ("; ".join(d["name"].strip() for d in others) or "none"))
        return
    for d in todo:
        title = re.sub(r'[\\/:*?"<>|]', " ", d["name"]).strip()
        r = s.get(f"{API}/files/{d['id']}/export", params={"mimeType": "text/html"})
        r.raise_for_status()
        if d["id"] not in synced and not SPECIAL.match(d["name"].strip()) and "॥".encode() not in r.content:
            skipped.append(d["name"])                             # not a page yet and no shlokas yet (an empty
            continue                                              # BG-N doc, notes): never made into a page
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{title}.html"
            path.write_bytes(r.content)
            real_wrap = uw.wrap
            uw.wrap = lambda t, data, folder, doc_id=None, _id=d["id"]: real_wrap(t, data, folder, doc_id or _id)
            try:
                done.append(uw.update_one(path, print))
            except uw.Problem as e:
                if not re.search(r"Don't know which page|not on the website yet", str(e)):
                    raise                                         # a real failure: stop, publish nothing
                skipped.append(d["name"])                         # not recorded: checked again next time
                continue
            finally:
                uw.wrap = real_wrap
        state[d["id"]] = d["modifiedTime"]
    if dry:
        return
    STATE.write_text(json.dumps(dict(sorted(state.items())), indent=1) + "\n", encoding="utf-8")
    if skipped:
        print("Skipped (not a page on the website" + ("" if allow_new else ", or a new chapter - tick"
              " 'Also add new chapters' to add those") + "): " + "; ".join(skipped))
    if done:
        print("Rebuilding the website…")
        uw.run("build.py", "home")
    Path(os.environ.get("GITHUB_OUTPUT", os.devnull)).open("a", encoding="utf-8").write(
        "summary=" + (", ".join(done) or "no page changes") + "\n")


if __name__ == "__main__":
    main()
