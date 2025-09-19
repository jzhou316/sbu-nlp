#!/usr/bin/env python3
"""
Fetch recent publications for multiple Google Scholar authors (by URL or ID) and
emit Hugo bundles for your site.

- Input: SCHOLAR_URLS env var (comma-separated), OR a file of URLs/IDs.
  Example URL: https://scholar.google.com/citations?user=X3JCGVIAAAAJ&hl=en
  We extract the 'user' param as the Scholar ID: X3JCGVIAAAAJ

- Filters by year >= YEAR_FROM (default 2024)
- Writes each paper as content/publication/<slug>/index.md
- Fills only the fields you want:
    title, authors, date, publishDate, draft=false,
    publication_types=["paper-conference"], publication="", url_pdf, image.preview_only=true
"""

import os
import re
import sys
import json
import time
import pathlib
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from typing import Iterable, List, Dict, Any
from slugify import slugify

from scholarly import scholarly, ProxyGenerator

# ----------------- CONFIG -----------------
YEAR_FROM = int(os.environ.get("YEAR_FROM", "2024"))
OUT_DIR   = pathlib.Path(os.environ.get("OUT_DIR", "content/publication"))
DRY_RUN   = os.environ.get("DRY_RUN", "0") == "1"
SLEEP_BETWEEN_AUTHORS = float(os.environ.get("SLEEP_BETWEEN_AUTHORS", "2.0"))  # seconds
# ------------------------------------------

def setup_scholar():
    """
    Optional: set up a proxy. Usually not needed locally.
    Running on CI can get rate-limited by Scholar.
    """
    # Example for Tor (if you know what you're doing):
    # pg = ProxyGenerator()
    # pg.Tor_Internal(tor_sock_port=9050, tor_control_port=9051, tor_password='YOUR_TOR_PASS')
    # scholarly.use_proxy(pg)
    pass

def extract_scholar_id(s: str) -> str:
    """
    Accepts either a full Scholar URL or a bare Scholar ID and returns the ID.
    """
    s = s.strip()
    if not s:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", s):
        # looks like a scholar id directly
        return s
    try:
        u = urlparse(s)
        q = parse_qs(u.query)
        uid = q.get("user", [""])[0]
        return uid
    except Exception:
        return ""

def read_inputs() -> List[str]:
    """
    Gather Scholar IDs from:
      - SCHOLAR_URLS env (comma-separated)
      - or first CLI arg pointing to a file with one URL/ID per line
      - or CLI args as URLs/IDs
    """
    ids = []

    env_urls = os.environ.get("SCHOLAR_URLS", "")
    if env_urls:
        for piece in env_urls.split(","):
            sid = extract_scholar_id(piece)
            if sid:
                ids.append(sid)

    if len(sys.argv) >= 2:
        arg = sys.argv[1]
        p = pathlib.Path(arg)
        if p.exists() and p.is_file():
            for line in p.read_text().splitlines():
                sid = extract_scholar_id(line)
                if sid:
                    ids.append(sid)
        else:
            # treat remaining args as IDs/URLs
            for a in sys.argv[1:]:
                sid = extract_scholar_id(a)
                if sid:
                    ids.append(sid)

    # Deduplicate while preserving order
    seen = set()
    out = []
    for sid in ids:
        if sid not in seen:
            out.append(sid)
            seen.add(sid)
    return out

def normalize_authors(bib_authors: str) -> List[str]:
    """
    Convert 'A. Author and B. Author' -> ['A. Author', 'B. Author']
    """
    if not bib_authors:
        return []
    parts = [p.strip() for p in re.split(r"\s+and\s+", bib_authors)]
    return [re.sub(r"\s*\.\s*", ". ", p).strip() for p in parts if p]

def year_to_iso(year: int) -> str:
    return f"{int(year):04d}-01-01T00:00:00Z"

def is_pdf_url(url: str) -> bool:
    return bool(url) and url.lower().endswith(".pdf")

def pick_pdf_url(pub: Dict[str, Any]) -> str:
    # eprint_url is often a direct PDF if present
    pdf = pub.get("eprint_url") or ""
    if is_pdf_url(pdf):
        return pdf
    # Sometimes pub_url points to a PDF
    purl = pub.get("pub_url") or ""
    if is_pdf_url(purl):
        return purl
    return ""  # leave blank if uncertain

def write_bundle(title: str, authors: List[str], year: int, pdf_url: str):
    """Write Hugo bundle with the exact front-matter structure you requested."""
    fm = []
    fm.append("---")
    # fm.append(f'title: "{title.replace(\'"\', r\'\\"\')}"')
    fm.append('title: "{}"'.format(title.replace('"', '\\"')))
    fm.append("authors:")
    for a in authors:
        fm.append('  - "{}"'.format(a.replace('"', '\\"')))
        # fm.append(f'  - "{a.replace(\'"\', r\'\\"\')}"')
    date_iso = year_to_iso(year)
    fm.append(f"date: '{date_iso}'")
    fm.append(f"publishDate: '{date_iso}'")
    fm.append("draft: false")
    # fm.append('publication_types: ["paper-conference"]')
    fm.append('publication: ""')
    fm.append(f'url_pdf: "{pdf_url}"' if pdf_url else 'url_pdf: ""')
    fm.append("image:")
    fm.append("  preview_only: true")
    fm.append("---\n")

    slug = slugify(f"{title[:80]}-{year}")
    dst_dir = OUT_DIR / slug
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "index.md"
    content = "\n".join(fm)

    if DRY_RUN:
        print(f"[DRY_RUN] Would write {dst}:\n{content}")
    else:
        dst.write_text(content, encoding="utf-8")
        print(f"Wrote {dst}")

def import_author_by_id(scholar_id: str, seen_titles: set):
    """
    Fetch publications for a single author by Scholar ID and write bundles for YEAR_FROM..now.
    """
    print(f"Fetching author: {scholar_id}")
    # scholarly.search_author_id returns an author object by ID
    author = scholarly.search_author_id(scholar_id)
    author = scholarly.fill(author, sections=["basics", "publications"])
    pubs = author.get("publications", []) or []
    cur_year = datetime.utcnow().year

    for p in pubs:
        try:
            p = scholarly.fill(p)
        except Exception as e:
            print(f"  warn: failed to fill a pub for {scholar_id}: {e}")
            continue

        bib = p.get("bib", {}) or {}
        title = (bib.get("title") or "").strip()
        if not title:
            continue

        # de-dupe by normalized title across all PIs we process
        norm_title = re.sub(r"\s+", " ", title.lower())
        if norm_title in seen_titles:
            continue

        # year
        yr = None
        for k in ("pub_year", "year"):
            v = bib.get(k)
            if v:
                try:
                    yr = int(v)
                    break
                except:
                    pass
        if not yr or yr < YEAR_FROM or yr > cur_year:
            continue

        # authors
        authors = normalize_authors(bib.get("author"))

        # pdf link if clearly a PDF
        pdf_url = pick_pdf_url(p)

        write_bundle(title=title, authors=authors, year=yr, pdf_url=pdf_url)
        seen_titles.add(norm_title)

def main():
    setup_scholar()
    ids = read_inputs()
    if not ids:
        print("No Scholar IDs/URLs provided.\n"
              "Set SCHOLAR_URLS env, pass a file path, or pass IDs/URLs as args.")
        print("Example:\n  SCHOLAR_URLS='https://scholar.google.com/citations?user=X3JCGVIAAAAJ' python scripts/import_scholar_multi.py")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    seen_titles = set()
    for sid in ids:
        try:
            import_author_by_id(sid, seen_titles)
        except Exception as e:
            print(f"Error with {sid}: {e}")
        time.sleep(SLEEP_BETWEEN_AUTHORS)

if __name__ == "__main__":
    main()
