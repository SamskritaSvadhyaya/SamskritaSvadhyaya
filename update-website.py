#!/usr/bin/env python3
"""One-click website update (for the owner, no commands needed).

In Google Docs: File -> Download -> Web page (.html, zipped). Then double-click
"Update website" on the desktop (runs this file), pick the downloaded file(s), and
it works out which page each doc is, rebuilds the site and publishes it.

Knows: every chapter import-drive.py knows (Narayaneeyam, Sundarakanda, KK,
Yudhdhakanda, Bhagavatam, Bhagavad Geeta), Raghuvamsha sargas, the Eclectic
Collection's KK Sarga 28, Shri Ganapati Atharvashirsha, "Geeta Themes" and
"Disclaimer and Credits". The doc is recognised by its file name (= the doc title).

    python update-website.py                 # window with a file picker
    python update-website.py FILE... [--no-publish]   # same, from the command line
"""

import base64
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "texts.json"
DEV = str.maketrans("0123456789", "०१२३४५६७८९")
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Problem(Exception):
    pass


# ---------------------------------------------------------------- helpers
def run(*cmd, py=True):
    """Run a command in the site folder; return its output; raise Problem if it fails."""
    full = [sys.executable, "-B", *cmd] if py else list(cmd)
    r = subprocess.run(full, cwd=ROOT, env=ENV, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    if r.returncode:
        raise Problem(f"{' '.join(cmd)} failed:\n{(r.stdout + r.stderr).strip()[-1500:]}")
    return r.stdout.strip()


def git(*args):
    return run("git", *args, py=False)


def read_download(path):
    """(doc title, html bytes) from a Google Docs download (.zip or .html)."""
    p = Path(path)
    title = re.sub(r"\s*\(\d+\)$", "", p.stem).replace("﻿", "").strip()   # "X (1).zip" -> "X"
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            pages = [n for n in z.namelist() if n.lower().endswith(".html")]
            if not pages:
                raise Problem(f"{p.name}: no web page inside this zip.")
            data = z.read(pages[0])
    elif p.suffix.lower() in (".html", ".htm"):
        data = p.read_bytes()
    else:
        raise Problem(f"{p.name}: choose the .zip from File -> Download -> Web page (.html, zipped).")
    return title, inline_classes(data)


def inline_classes(data):
    """A browser download keeps the doc's formatting in a <style> list of classes (.c12{…});
    the Drive export the importers were written for has it inline (style="…"). Copy each
    class's rules (and the plain p/h1…/li rules) onto the elements, so both read the same."""
    text = data.decode("utf-8")
    m = re.search(r"<style[^>]*>(.*?)</style>", text, re.S)
    if not m or not re.search(r'class="[^"]*\bc\d+', text):
        return data
    css = re.sub(r"@import[^;]*;", "", m.group(1))
    cls, tag = {}, {}
    for sel, rules in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for s in sel.split(","):
            s = s.strip()
            if re.fullmatch(r"\.c\d+", s):
                cls[s[1:]] = cls.get(s[1:], "") + rules.strip().rstrip(";") + ";"
            elif re.fullmatch(r"p|h[1-6]|li", s):
                tag[s] = tag.get(s, "") + rules.strip().rstrip(";") + ";"

    def fix(mt):
        name, attrs = mt.group(1), mt.group(2)
        cm = re.search(r'\sclass="([^"]*)"', attrs)
        if not cm:
            return mt.group(0)
        style = tag.get(name.lower(), "") + "".join(cls.get(c, "") for c in cm.group(1).split())
        if not style:
            return mt.group(0)
        sm = re.search(r'\sstyle="([^"]*)"', attrs)
        if sm:                                                 # the element's own style wins
            attrs = attrs.replace(sm.group(0), "")
            style += sm.group(1)
        attrs = attrs.replace(cm.group(0), "")
        return f'<{name}{attrs} style="{html.escape(style, quote=True)}">'

    body_at = text.find("<body")
    head, body = text[:body_at], text[body_at:]
    body = re.sub(r"<(\w+)(\s[^<>]*?)?>", lambda mt: fix(mt) if mt.group(2) else mt.group(0), body)
    return (head + body).encode("utf-8")


def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def entry(slug):
    return next(e for e in manifest() if e["slug"] == slug)


def wrap(title, data, folder, doc_id=None):
    """Write the download as the JSON that import-drive.py / gdoc_to_body.py / themes.py read."""
    j = Path(folder) / "download.json"
    j.write_text(json.dumps({"title": title, "mimeType": "text/html", "id": doc_id,
                             "content": base64.b64encode(data).decode()}), encoding="utf-8")
    return str(j)


def body_from(download_json, folder):
    out = Path(folder) / "body.html"
    out.write_text(run("gdoc_to_body.py", download_json, str(Path(folder) / "media")), encoding="utf-8")
    return str(out)


# ---------------------------------------------------------------- Disclaimer and Credits
def disclaimer_body(data):
    """The doc's paragraphs and numbered lists as _disclaimer_body.html (word for word)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data.decode("utf-8"), "html.parser")
    body = soup.body
    for div in body.find_all("div", recursive=False):     # page header / footer
        div.decompose()

    from urllib.parse import unquote
    MARK = "\u0001"                                          # keeps finished link HTML apart from text

    def inline(node):
        out = []
        for a in node.find_all("a"):                           # links: real address, opens in a new tab
            href = a.get("href", "")
            m = re.match(r"https?://www\.google\.com/url\?q=([^&]+)", href)
            a.replace_with(soup.new_string(
                f'{MARK}<a href="{html.escape(unquote(m.group(1)) if m else href)}" target="_blank" '
                f'rel="noopener">{html.escape(a.get_text(), quote=False)}</a>{MARK}'))
        for span in node.find_all("span") or [node]:
            pieces = span.get_text().split(MARK)
            text = "".join(x if i % 2 else html.escape(x, quote=False) for i, x in enumerate(pieces))
            if text.strip() and re.search(r"font-weight:\s*(700|bold)", span.get("style", "")):
                text = f"<strong>{text.strip()}</strong>"
            out.append(text)
        return re.sub(r"\s+", " ", "".join(out).replace("\xa0", " ")).strip()

    blocks = []                                                # (kind, html)
    for el in body.find_all(["p", "ol", "ul"], recursive=False):
        if el.name == "p":
            text = inline(el)
            if text:
                centred = "text-align:center" in el.get("style", "").replace(" ", "")
                blocks.append(("p", f'<p style="text-align:center">{text}</p>' if centred else f"<p>{text}</p>"))
        else:
            items = "".join(f"<li>{inline(li)}</li>\n" for li in el.find_all("li"))
            if blocks and blocks[-1][0] == "ol":                # Google splits one list into several <ol>
                blocks[-1] = ("ol", blocks[-1][1].replace("</ol>", items + "</ol>"))
            else:
                blocks.append(("ol", f'<ol class="source-list">\n{items}</ol>'))
    out = ""
    for i, (kind, h) in enumerate(blocks):
        if i:
            out += "\n" if kind == "ol" else "\n\n"            # a list sits tight under its paragraph
        out += h
    return out + "\n"


# ---------------------------------------------------------------- one document
def update_one(path, log):
    title, data = read_download(path)
    log(f"• {title}")
    with tempfile.TemporaryDirectory() as tmp:
        if re.fullmatch(r"Geeta\s+Themes", title, re.I):
            out = run("themes.py", "import", wrap(title, data, tmp))
            log("  Geeta Themes: " + out.splitlines()[-1].split(";")[0])
            return "Geeta Themes"

        if re.fullmatch(r"Disclaimer\s+and\s+Credits", title, re.I):
            (ROOT / "_disclaimer_body.html").write_text(disclaimer_body(data), encoding="utf-8")
            log("  Disclaimer and Credits page updated.")
            return "Disclaimer and Credits"

        if re.search(r"Ganapati\s+Atharvashirsha", title, re.I):
            e = entry("ganapati-atharvashirsha")
            j = wrap(title, data, tmp, e.get("doc"))
            run("build.py", "page", "--slug", e["slug"], "--title", e["title"], "--title-sa", e["title_sa"],
                "--subtitle", "", "--body", body_from(j, tmp), *(["--doc", e["doc"]] if e.get("doc") else []))
            log("  Shri Ganapati Atharvashirsha updated.")
            return e["title"]

        m = re.search(r"Raghuvamsha\s*-\s*Sarga\s+(\d+)", title, re.I)
        if m:
            n = int(m.group(1))
            c = next((c for c in entry("raghuvamsha").get("chapters", []) if c["n"] == n), None)
            if c is None:
                raise Problem(f"Raghuvamsha Sarga {n} is not on the website yet - adding a new sarga needs help.")
            j = wrap(title, data, tmp, c.get("doc"))
            run("build.py", "page", "--work", "raghuvamsha", "--slug", c["slug"], "--n", str(n),
                "--title", c["title"], "--title-sa", c["title_sa"], "--body", body_from(j, tmp),
                *(["--doc", c["doc"]] if c.get("doc") else []))
            run("build.py", "work-index", "--slug", "raghuvamsha")
            log(f"  Raghuvamsha Sarga {n} updated.")
            return f"Raghuvamsha Sarga {n}"

        if re.match(r"KK\s*-\s*Sarga\s*28\b", title, re.I):          # lives in the Eclectic Collection
            c = next(c for c in entry("eclectic-collection")["chapters"] if c["slug"] == "kishkindhakanda-sarga-28")
            j = wrap(title, data, tmp, c.get("doc"))
            body = body_from(j, tmp)
            run("build.py", "page", "--work", "eclectic-collection", "--slug", c["slug"], "--n", str(c["n"]),
                "--title", c["title"], "--title-sa", c["title_sa"], "--body", body,
                *(["--doc", c["doc"]] if c.get("doc") else []))
            run("build.py", "work-index", "--slug", "eclectic-collection")
            log("  Eclectic Collection: Kishkindhakanda Sarga 28 updated.")
            return "Kishkindhakanda Sarga 28"

        # Every other chapter: import-drive.py knows it from the title (or says it doesn't).
        j = wrap(title, data, tmp)
        try:
            run("import-drive.py", j, "--dry-run")
        except Problem:
            raise Problem(f"Don't know which page '{title}' is.\n"
                          "Keep the file name exactly as Google Docs saves it (the doc's title).")
        out = run("import-drive.py", j)
        for line in out.splitlines():
            log("  " + line.strip())
        return title


def update(paths, log, publish=True):
    if publish and git("status", "--porcelain"):
        raise Problem("The website folder has unpublished changes from before.\n"
                      "Nothing was changed. Ask for help (see the guide).")
    if publish:
        log("Getting the latest website from GitHub…")
        git("pull", "--ff-only")
    done = [update_one(p, log) for p in paths]
    log("Rebuilding the website…")
    run("build.py", "home")
    if not publish:
        log("Done (not published).")
        return
    if not git("status", "--porcelain"):
        log("Nothing changed - the website already matches these docs.")
        return
    git("add", "-A")
    git("commit", "-q", "-m", "Update from Google Docs: " + ", ".join(done))
    log("Publishing…")
    git("push", "-q")
    log("\nDone! The website will show the changes in about a minute.\n"
        "(If a page still looks old, press Ctrl + Shift + R.)")


# ---------------------------------------------------------------- window
def gui():
    import threading
    import tkinter as tk
    from tkinter import filedialog, scrolledtext

    win = tk.Tk()
    win.title("Update Samskrita Svadhyaya")
    win.geometry("640x420")
    tk.Label(win, text="In Google Docs: File → Download → Web page (.html, zipped).\n"
                       "Then choose the downloaded file(s) here.", font=("Segoe UI", 11), pady=10).pack()
    box = scrolledtext.ScrolledText(win, font=("Consolas", 10), height=16, state="disabled")
    box.pack(fill="both", expand=True, padx=10)

    def log(msg):
        def add():
            box.configure(state="normal")
            box.insert("end", msg + "\n")
            box.see("end")
            box.configure(state="disabled")
        win.after(0, add)

    def work(paths):
        try:
            update(paths, log)
        except Exception as e:                                   # noqa: BLE001 - show anything to the owner
            log(f"\nSomething went wrong - nothing was published.\n{e}")
            try:
                git("reset", "-q", "--hard")                     # undo half-made changes
                git("clean", "-q", "-fd", "--", ".")
            except Exception:                                    # noqa: BLE001
                pass
        win.after(0, lambda: button.configure(state="normal"))

    def choose():
        downloads = Path.home() / "Downloads"
        paths = filedialog.askopenfilenames(
            title="Choose the downloaded Google Doc(s)",
            initialdir=str(downloads if downloads.exists() else Path.home()),
            filetypes=[("Google Docs web page", "*.zip *.html"), ("All files", "*.*")])
        if paths:
            button.configure(state="disabled")
            threading.Thread(target=work, args=(paths,), daemon=True).start()

    button = tk.Button(win, text="Choose downloaded file(s)…", font=("Segoe UI", 11), command=choose, padx=12)
    button.pack(pady=10)
    win.mainloop()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--no-publish"]
    if args:
        try:
            update(args, print, publish="--no-publish" not in sys.argv)
        except Problem as e:
            raise SystemExit(str(e))
    else:
        gui()
