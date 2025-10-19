#!/usr/bin/env python3
"""
Fetch recent publications for multiple Google Scholar authors (by URL or ID) and
emit Hugo bundles for your site.

Changes vs your version:
- publication field: conference/journal if present; else "arXiv" if arXiv; else ""  ### NEW
- cross-author merging of (near-)duplicate titles by "information richness"        ### NEW
"""

import os
import re
import sys
import json
import time
import pathlib
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from typing import Iterable, List, Dict, Any, Optional, Tuple
from slugify import slugify

from scholarly import scholarly, ProxyGenerator

# ----------------- CONFIG -----------------
YEAR_FROM = int(os.environ.get("YEAR_FROM", "2024"))
OUT_DIR   = pathlib.Path(os.environ.get("OUT_DIR", "/home/huajzhang/pub"))
DRY_RUN   = os.environ.get("DRY_RUN", "0") == "1"
SLEEP_BETWEEN_AUTHORS = float(os.environ.get("SLEEP_BETWEEN_AUTHORS", "5.0"))  # seconds
# ------------------------------------------

import requests
from urllib.parse import urlparse, parse_qs

_HTTP_TIMEOUT = 10
_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ScholarFetcher/1.0; +https://example.org)"
}


import unicodedata, html

_TAG_RE = re.compile(r"<[^>]+>")

def sanitize_text(s: str) -> str:
    if not s:
        return s
    # 1) Remove any HTML tags Scholar might leak
    s = _TAG_RE.sub("", s)
    # 2) Unescape HTML entities (&amp; → &)
    s = html.unescape(s)
    # 3) Normalize Unicode: fold math/compat chars to plain ASCII letters
    s = unicodedata.normalize("NFKC", s)
    # 4) Drop zero-width & odd control chars
    s = s.replace("\u200b", "").replace("\ufeff", "").replace("\u200c", "").replace("\u200d", "")
    # 5) Optional: strip residual combining marks that sometimes encircle/overlay letters
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    # 6) Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_likely_pdf_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    if u.endswith(".pdf"):
        return True
    return any((
        "openreview.net/pdf" in u,
        "/doi/pdf" in u,
        "ieeexplore.ieee.org/stamp/stamp.jsp" in u,
        "arxiv.org/pdf/" in u,
        "aclanthology.org/" in u and u.rsplit("/", 1)[-1].endswith(".pdf"),
    ))

def rewrite_to_direct_pdf(url: str) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url)
        host = p.netloc.lower()

        if "arxiv.org" in host:
            if p.path.startswith("/abs/"):
                paper_id = p.path.split("/abs/", 1)[1]
                return f"https://arxiv.org/pdf/{paper_id}.pdf"
            if p.path.startswith("/pdf/") and not p.path.endswith(".pdf"):
                return url + ".pdf"

        if "openreview.net" in host:
            q = parse_qs(p.query)
            if p.path.startswith("/forum") and "id" in q:
                return f"https://openreview.net/pdf?id={q['id'][0]}"

        if "dl.acm.org" in host and p.path.startswith("/doi/") and "/doi/pdf/" not in p.path:
            return url.replace("/doi/", "/doi/pdf/")

        if "ieeexplore.ieee.org" in host and "/document/" in p.path:
            doc_id = p.path.strip("/").split("/")[-1]
            return f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={doc_id}"

        if "aclanthology.org" in host:
            parts = p.path.strip("/").split("/")
            if len(parts) == 1 and not parts[0].endswith(".pdf"):
                return f"https://aclanthology.org/{parts[0]}.pdf"

        return url
    except Exception:
        return url

def serves_pdf(url: str) -> bool:
    try:
        r = requests.head(url, allow_redirects=True, timeout=_HTTP_TIMEOUT, headers=_HTTP_HEADERS)
        ctype = r.headers.get("Content-Type", "").lower()
        if "application/pdf" in ctype:
            return True
    except Exception:
        pass
    try:
        r = requests.get(url, stream=True, allow_redirects=True, timeout=_HTTP_TIMEOUT, headers=_HTTP_HEADERS)
        ctype = r.headers.get("Content-Type", "").lower()
        return "application/pdf" in ctype
    except Exception:
        return False

def setup_scholar():
    """
    Use FreeProxies rotation built into scholarly.
    No extra installation needed.
    """
    
    pg = ProxyGenerator()
    if pg.FreeProxies():
        scholarly.use_proxy(pg)
        print("Proxy rotation enabled (FreeProxies).")
    else:
        print("Warning: could not fetch free proxies; continuing without proxy.")

def extract_scholar_id(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", s):
        return s
    try:
        u = urlparse(s)
        q = parse_qs(u.query)
        uid = q.get("user", [""])[0]
        return uid
    except Exception:
        return ""

def read_inputs() -> List[str]:
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
            for a in sys.argv[1:]:
                sid = extract_scholar_id(a)
                if sid:
                    ids.append(sid)

    # Dedup while preserving order
    seen = set()
    out = []
    for sid in ids:
        if sid not in seen:
            out.append(sid)
            seen.add(sid)
    return out

def normalize_authors(bib_authors: str) -> List[str]:
    if not bib_authors:
        return []
    parts = [p.strip() for p in re.split(r"\s+and\s+", bib_authors)]
    return [re.sub(r"\s*\.\s*", ". ", p).strip() for p in parts if p]

def year_to_iso(year: int) -> str:
    return f"{int(year):04d}-01-01T00:00:00Z"

def is_pdf_url(url: str) -> bool:
    return bool(url) and url.lower().endswith(".pdf")

def pick_pdf_url(pub: Dict[str, Any]) -> str:
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

    for u in uniq:
        if serves_pdf(u):
            return u
    for u in uniq:
        if is_likely_pdf_url(u):
            return u
    return ""

# ---------- NEW: venue/arXiv inference + duplicate merging helpers ----------

def infer_publication_string(bib: Dict[str, Any], pub: Dict[str, Any]) -> str:
    """
    Prefer explicit venue/journal/booktitle. If none and looks like arXiv, return 'arXiv'.
    Else ''.
    """
    for k in ("journal", "venue", "booktitle"):
        v = (bib.get(k) or "").strip()
        if v:
            return v
    # Some entries mark arXiv as journal or in URL
    j = (bib.get("journal") or "").lower()
    if "arxiv" in j:
        return "arXiv"
    for key in ("eprint_url", "pub_url", "url"):
        u = (pub.get(key) or "").lower()
        if "arxiv.org" in u:
            return "arXiv"
    return ""

def normalize_title_key(title: str) -> str:
    """
    Lowercase, remove non-alnum, compress spaces — good for equality/substring tests.
    """
    t = title.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def titles_overlap(a: str, b: str) -> bool:
    """
    Consider as same if equal or one is a substring of the other after normalization.
    """
    A, B = normalize_title_key(a), normalize_title_key(b)
    return A == B or A in B or B in A

def info_richness_score(bib: Dict[str, Any], pdf_url: str, publication: str) -> int:
    """
    Heuristic: prefer entries with venue/DOI/pages/volume/number/authors and a verified PDF.
    """
    score = 0
    if publication: score += 5           # having a venue is the strongest signal
    if bib.get("doi"): score += 3
    if bib.get("pages"): score += 2
    if bib.get("volume"): score += 1
    if bib.get("number"): score += 1
    if (bib.get("author") or "").strip(): score += 1
    if pdf_url: score += 2
    # tiny boost for longer title (often the camera-ready full title)
    title = (bib.get("title") or "")
    score += min(len(title), 120) // 40
    return score

# Structure we keep while merging
class PubRecord:
    def __init__(self,
                 title: str,
                 authors: List[str],
                 year: int,
                 pdf_url: str,
                 publication: str,
                 bib: Dict[str, Any]):
        self.title = title
        self.authors = authors
        self.year = year
        self.pdf_url = pdf_url
        self.publication = publication
        self.bib = bib

    def richness(self) -> int:
        return info_richness_score(self.bib, self.pdf_url, self.publication)

# ---------------------------------------------------------------------------

def write_bundle(title: str, authors: List[str], year: int, pdf_url: str, publication: str):
    """Write Hugo bundle; same structure as yours, now with publication filled."""
    fm = []
    fm.append("---")
    fm.append('title: "{}"'.format(title.replace('"', '\\"')))
    fm.append("authors:")
    for a in authors:
        fm.append('  - "{}"'.format(a.replace('"', '\\"')))
    date_iso = year_to_iso(year)
    fm.append(f"date: '{date_iso}'")
    fm.append(f"publishDate: '{date_iso}'")
    fm.append("draft: false")
    fm.append('publication: "{}"'.format(publication.replace('"', '\\"') if publication else ""))
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

def import_author_by_id_collect(scholar_id: str, seen_titles: set) -> List[PubRecord]:
    """
    Fetch publications for a single author and return PubRecord list (no writing here).
    """
    out: List[PubRecord] = []

    print(f"Fetching author: {scholar_id}")
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
        title = sanitize_text(raw_title)
        # title = (bib.get("title") or "").strip()
        if not title:
            continue

        # dedupe exact-normalized titles across all PIs (legacy guard)
        norm_title = re.sub(r"\s+", " ", title.lower())
        # (keep collecting; cross-author merge will handle overlaps later)
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

        authors = normalize_authors(bib.get("author"))
        pdf_url = pick_pdf_url(p)
        if pdf_url:
            print(f"  ✔ PDF: {pdf_url}")
        else:
            print(f"  ✖ No PDF for: {title}")

        publication = infer_publication_string(bib, p)  # NEW

        out.append(PubRecord(
            title=title,
            authors=authors,
            year=yr,
            pdf_url=pdf_url,
            publication=publication,
            bib=bib
        ))

    return out

def merge_pub_lists(records: List[PubRecord]) -> List[PubRecord]:
    """
    Merge near-duplicate titles: keep the one with more information.
    """
    kept: List[PubRecord] = []
    for rec in records:
        matched_idx: Optional[int] = None
        for i, old in enumerate(kept):
            if titles_overlap(rec.title, old.title):
                matched_idx = i
                break
        if matched_idx is None:
            kept.append(rec)
        else:
            old = kept[matched_idx]
            # Decide which one to keep
            if rec.richness() > old.richness():
                kept[matched_idx] = rec
            else:
                # If richness ties, keep the one with longer title or (as tiebreaker) newer year
                if rec.richness() == old.richness():
                    if len(rec.title) > len(old.title) or rec.year > old.year:
                        kept[matched_idx] = rec
                    # else keep old
                # else keep old
            # Optionally, we could union author lists; you asked to keep names as-is,
            # but richer entry likely already has the full list.
    return kept

def main():
    setup_scholar()
    ids = read_inputs()
    if not ids:
        print("No Scholar IDs/URLs provided.\n"
              "Set SCHOLAR_URLS env, pass a file path, or pass IDs/URLs as args.")
        print("Example:\n  SCHOLAR_URLS='https://scholar.google.com/citations?user=X3JCGVIAAAAJ' python scripts/import_scholar_multi.py")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Collect all records first (no writing)
    all_records: List[PubRecord] = []
    seen_titles = set()  # kept for your legacy flow; not strictly necessary now
    for sid in ids:
        try:
            recs = import_author_by_id_collect(sid, seen_titles)
            all_records.extend(recs)
        except Exception as e:
            print(f"Error with {sid}: {e}")
        time.sleep(SLEEP_BETWEEN_AUTHORS)

    # Merge duplicates / substrings by information richness  ### NEW
    merged = merge_pub_lists(all_records)

    # Finally, write bundles
    for rec in merged:
        write_bundle(
            title=rec.title,
            authors=rec.authors,
            year=rec.year,
            pdf_url=rec.pdf_url,
            publication=rec.publication
        )

if __name__ == "__main__":
    main()
