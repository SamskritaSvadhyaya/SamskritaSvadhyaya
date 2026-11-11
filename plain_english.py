"""Write Sanskrit words in plain English instead of IAST diacritics (the owner's style):
Raghuvaṃśa -> Raghuvamsha, Kālidāsa -> Kalidasa, Vṛndāvana -> Vrindavana, Śrīla -> Shrila.

Only Latin letters with Sanskrit diacritics are changed; Devanagari and everything else is
left alone. Used by gdoc_to_body.py on every upload, and runnable on the whole site:

    python plain_english.py            # fix texts.json, note sources and every page
"""
import re

_MAP = {
    "ā": "a", "Ā": "A", "ī": "i", "Ī": "I", "ū": "u", "Ū": "U",
    "ṛ": "ri", "Ṛ": "Ri", "ṝ": "ri", "Ṝ": "Ri", "ḷ": "li", "Ḷ": "Li", "ḹ": "li",
    "ṃ": "m", "Ṃ": "M", "ṁ": "m", "Ṁ": "M", "ḥ": "h", "Ḥ": "H",
    "ś": "sh", "Ś": "Sh", "ṣ": "sh", "Ṣ": "Sh",
    "ṇ": "n", "Ṇ": "N", "ñ": "n", "Ñ": "N", "ṅ": "n", "Ṅ": "N",
    "ṭ": "t", "Ṭ": "T", "ḍ": "d", "Ḍ": "D",
}
_RE = re.compile("[" + "".join(_MAP) + "]")


def plain(text):
    return _RE.sub(lambda m: _MAP[m.group(0)], text)


def main():
    import glob
    import os
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)
    files = ["texts.json"] + glob.glob("*.html") + glob.glob("**/index.html", recursive=True)
    changed = 0
    for f in files:
        f = f.replace(os.sep, "/")
        if f.startswith(("_unreleased/", ".git/")) or f == "googleeeb64c879486498d.html":
            continue
        raw = open(f, "rb").read()
        text = raw.decode("utf-8")
        new = plain(text)
        if new != text:
            open(f, "wb").write(new.encode("utf-8"))
            changed += 1
    print(f"plain English spelling: {changed} file(s) updated")


if __name__ == "__main__":
    main()
