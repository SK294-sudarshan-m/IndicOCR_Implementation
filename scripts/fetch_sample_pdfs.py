"""Download small, real, fully-scanned PDFs from the Internet Archive into input/ (default).

    python scripts/fetch_sample_pdfs.py [--dest input] [--count 5] [--max-pages 5] [--max-kb 1200]

Keeps a PDF only if every page holds an image, it is short, and its title/text pass a spam filter (the Archive
hosts many junk uploads). Licences are not checked: treat the files as private test material.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

import pymupdf

SPAM = re.compile(r"xxx|porn|sex|18\+|viral|video|nude|escort|casino|betting|leak|codes|boosters|reward|coins|hack|generator|apk|crypto|loan|free|download|gift", re.I)


def get(url: str, binary: bool = False):
    request = urllib.request.Request(url, headers={"User-Agent": "docpipe-sample-fetch/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    return data if binary else json.loads(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=Path("input"))
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--max-kb", type=int, default=1200)
    args = parser.parse_args()
    args.dest.mkdir(parents=True, exist_ok=True)
    max_bytes = args.max_kb * 1024

    query = f'mediatype:texts AND imagecount:[1 TO {args.max_pages}] AND format:"Text PDF" AND item_size:[30000 TO {max_bytes}] AND language:English'
    url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(
        {"q": query, "fl[]": ["identifier", "title", "item_size"], "rows": 300, "sort[]": "downloads desc", "output": "json"}, doseq=True
    )
    docs = [d for d in get(url)["response"]["docs"] if " " in str(d.get("title", "")) and not SPAM.search(d["identifier"] + " " + str(d.get("title")))]
    docs.sort(key=lambda d: int(d.get("item_size", 10**9)))

    kept = 0
    for d in docs:
        if kept == args.count:
            break
        ident = d["identifier"]
        target = args.dest / f"{ident}.pdf"
        if target.exists():
            continue
        try:
            files = get(f"https://archive.org/metadata/{ident}")["files"]
            pdfs = [f for f in files if f["name"].lower().endswith(".pdf") and f.get("format") in ("Text PDF", "Image Container PDF") and 10_000 < int(f.get("size", 0)) < max_bytes]
            if not pdfs:
                continue
            best = min(pdfs, key=lambda f: int(f["size"]))
            target.write_bytes(get(f"https://archive.org/download/{ident}/{urllib.parse.quote(best['name'])}", binary=True))
            with pymupdf.open(target) as doc:
                text = " ".join(page.get_text() for page in doc)
                ok = 1 <= doc.page_count <= args.max_pages and all(page.get_images() for page in doc) and not SPAM.search(text) and len(re.findall(r"[A-Za-z]{4,}", text)) >= 25
                pages = doc.page_count
            if not ok:
                target.unlink()
                continue
            kept += 1
            print(f"{ident}: {pages} pages, {target.stat().st_size // 1024} KB, https://archive.org/details/{ident}")
        except Exception as exc:  # one bad item must not stop the search
            print("skip", ident, type(exc).__name__)
            if target.exists() and target.stat().st_size == 0:
                target.unlink()
    print(f"{kept} PDF(s) downloaded to {args.dest}")


if __name__ == "__main__":
    main()
