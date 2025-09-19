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



import requests
from urllib.parse import urlparse, parse_qs, urlunparse

# Accept generous timeouts so we don't hang CI
_HTTP_TIMEOUT = 10
_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ScholarFetcher/1.0; +https://example.org)"
}

def is_likely_pdf_url(url: str) -> bool:
    """Heuristic: .pdf or known providers' PDF endpoints."""
    if not url:
        return False
    u = url.lower()
    if u.endswith(".pdf"):
        return True
    return any((
        "openreview.net/pdf" in u,
        "/doi/pdf" in u,                     # ACM DL, some publishers
        "ieeexplore.ieee.org/stamp/stamp.jsp" in u,
        "arxiv.org/pdf/" in u,
        "aclanthology.org/" in u and u.rsplit("/", 1)[-1].endswith(".pdf"),
    ))

def rewrite_to_direct_pdf(url: str) -> str:
    """Map common landing pages to direct PDF links."""
    if not url:
        return ""
    try:
        p = urlparse(url)
        host = p.netloc.lower()

        # arXiv: /abs/ -> /pdf/{id}.pdf
        if "arxiv.org" in host:
            if p.path.startswith("/abs/"):
                paper_id = p.path.split("/abs/", 1)[1]
                return f"https://arxiv.org/pdf/{paper_id}.pdf"
            if p.path.startswith("/pdf/") and not p.path.endswith(".pdf"):
                return url + ".pdf"

        # OpenReview: forum?id=... -> pdf?id=...
        if "openreview.net" in host:
            q = parse_qs(p.query)
            if p.path.startswith("/forum") and "id" in q:
                return f"https://openreview.net/pdf?id={q['id'][0]}"
            # already a /pdf?id=... is fine

        # ACM DL: /doi/{doi} -> /doi/pdf/{doi}
        if "dl.acm.org" in host and p.path.startswith("/doi/") and "/doi/pdf/" not in p.path:
            return url.replace("/doi/", "/doi/pdf/")

        # IEEE Xplore: /document/{id} -> /stamp/stamp.jsp?tp=&arnumber={id}
        if "ieeexplore.ieee.org" in host and "/document/" in p.path:
            doc_id = p.path.strip("/").split("/")[-1]
            return f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={doc_id}"

        # ACL Anthology: ensure trailing .pdf
        if "aclanthology.org" in host:
            # page like /P24-1234/ -> /P24-1234.pdf
            parts = p.path.strip("/").split("/")
            if len(parts) == 1 and not parts[0].endswith(".pdf"):
                return f"https://aclanthology.org/{parts[0]}.pdf"

        # Springer/Elsevier/Wiley often need redirects; keep original
        return url
    except Exception:
        return url

def serves_pdf(url: str) -> bool:
    """HEAD (then light GET if HEAD unhelpful) to see if it's a PDF."""
    try:
        r = requests.head(url, allow_redirects=True, timeout=_HTTP_TIMEOUT, headers=_HTTP_HEADERS)
        ctype = r.headers.get("Content-Type", "").lower()
        if "application/pdf" in ctype:
            return True
    except Exception:
        pass
    # Some hosts don't honor HEAD properly
    try:
        r = requests.get(url, stream=True, allow_redirects=True, timeout=_HTTP_TIMEOUT, headers=_HTTP_HEADERS)
        ctype = r.headers.get("Content-Type", "").lower()
        return "application/pdf" in ctype
    except Exception:
        return False


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
    """
    Prefer a verified PDF link. Try eprint_url first, then pub_url.
    1) Rewrite common hosts to direct PDF.
    2) Verify by Content-Type if possible.
    3) If verification fails but it still looks like a PDF endpoint, accept it.
    """
    candidates = []
    for key in ("eprint_url", "pub_url"):
        val = (pub.get(key) or "").strip()
        if not val:
            continue
        val2 = rewrite_to_direct_pdf(val)
        candidates.extend([val2, val]) if val2 != val else candidates.append(val)

    # Dedup while preserving order
    seen = set()
    uniq = []
    for u in candidates:
        if u and u not in seen:
            uniq.append(u)
            seen.add(u)

    # Try verified-first
    for u in uniq:
        if serves_pdf(u):
            return u

    # Fall back to heuristic "likely PDF" even if HEAD/GET didn't cooperate
    for u in uniq:
        if is_likely_pdf_url(u):
            return u

    # Last resort: no pdf; return empty and let Hugo show no PDF button
    return ""

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

        if pdf_url:
            print(f"  ✔ PDF: {pdf_url}")
        else:
            print(f"  ✖ No PDF for: {title}")


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
