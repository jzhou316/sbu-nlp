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
import random
from scholarly import scholarly, ProxyGenerator
# from scholarly._proxy_generator import MaxTriesExceededException  # optional

# ----------------- CONFIG -----------------
YEAR_FROM = int(os.environ.get("YEAR_FROM", "2020"))
OUT_DIR   = pathlib.Path(os.environ.get("OUT_DIR", "/home/huajzhang/pub"))
DRY_RUN   = os.environ.get("DRY_RUN", "0") == "1"
SLEEP_BETWEEN_AUTHORS = float(os.environ.get("SLEEP_BETWEEN_AUTHORS", "5.0"))  # seconds

CACHE_DIR = pathlib.Path(os.environ.get("CACHE_DIR", "/home/huajzhang/pub_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------

import requests
from urllib.parse import urlparse, parse_qs

_HTTP_TIMEOUT = 10
_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ScholarFetcher/1.0; +https://example.org)"
}


import unicodedata, html

_TAG_RE = re.compile(r"<[^>]+>")


_PDF_OK = {}  # url -> bool

_BIBTEX_MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

def serves_pdf_cached(url: str) -> bool:
    if url in _PDF_OK:
        return _PDF_OK[url]
    ok = serves_pdf(url)
    _PDF_OK[url] = ok
    return ok


def month_from_arxiv_bib(bib: dict) -> int | None:
    """
    Extract month from modern arXiv IDs like arXiv:2212.10509 -> month=12.
    Returns 1..12 or None.
    """
    hay = " ".join([
        str(bib.get("journal", "") or ""),
        str(bib.get("citation", "") or ""),
        str(bib.get("eprint", "") or ""),
        str(bib.get("url", "") or ""),
    ])

    # Modern arXiv IDs: YYMM.NNNNN (optionally with v2, v3...)
    m = re.search(r"arxiv:\s*(\d{2})(\d{2})\.\d{4,5}(?:v\d+)?", hay, re.IGNORECASE)
    if not m:
        return None

    mm = int(m.group(2))
    return mm if 1 <= mm <= 12 else None
def cache_path_for_author(scholar_id: str) -> pathlib.Path:
    return CACHE_DIR / f"scholar_{scholar_id}.jsonl"

def load_author_cache(scholar_id: str) -> tuple[list["PubRecord"], set[str]]:
    """
    Return (records, title_keys).
    """
    path = cache_path_for_author(scholar_id)
    recs: list[PubRecord] = []
    keys: set[str] = set()
    if not path.exists():
        return recs, keys

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            title = obj.get("title") or ""
            if not title:
                continue
            rec = PubRecord(
                title=title,
                authors=obj.get("authors") or [],
                year=int(obj.get("year")),
                month=int(obj.get("month", 1)),
                day=int(obj.get("day", 1)),
                pdf_url=obj.get("pdf_url") or "",
                publication=obj.get("publication") or "",
                bib=obj.get("bib") or {},   # optional, can be {}
            )
            recs.append(rec)
            keys.add(normalize_title_key(title))
        except Exception:
            # Ignore malformed line; JSONL allows partial corruption without losing whole file
            continue
    return recs, keys

def append_author_cache(scholar_id: str, rec: "PubRecord"):
    path = cache_path_for_author(scholar_id)
    obj = {
        "title": rec.title,
        "authors": rec.authors,
        "year": rec.year,
        "month": rec.month,
        "day": rec.day,
        "pdf_url": rec.pdf_url,
        "publication": rec.publication,
        # keep bib optional; can help later debugging/dedup
        "bib": rec.bib,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def parse_bibtex_month(bibtex: str) -> int | None:
    if not bibtex:
        return None
    m = re.search(r"\bmonth\s*=\s*[{\"']?([A-Za-z]+|\d{1,2})", bibtex, re.IGNORECASE)
    if not m:
        return None
    val = m.group(1).strip().lower()
    if val.isdigit():
        mm = int(val)
        return mm if 1 <= mm <= 12 else None
    return _BIBTEX_MONTH_MAP.get(val)


def resolve_pub_date_ymd(*, year: int, pub_obj, bib: dict) -> tuple[int, int, int]:
    # 1) BibTeX month
    try:
        bibtex = scholarly.bibtex(pub_obj)
        mm = parse_bibtex_month(bibtex)
        if mm:
            return (year, mm, 1)
    except Exception:
        pass

    # 2) arXiv month from bib strings (YYMM...)
    mm = month_from_arxiv_bib(bib)
    if mm:
        return (year, mm, 1)

    # 3) fallback
    return (year, 1, 1)

def ymd_to_hugo_iso(y: int, m: int, d: int) -> str:
    return f"{y:04d}-{m:02d}-{d:02d}T00:00:00Z"

def fill_with_backoff(obj, *, max_tries=6, base=2.0, jitter=0.5):
    """
    Exponential backoff for scholarly.fill().
    Keeps behavior polite: fewer retries, longer waits, random jitter.
    """
    for t in range(max_tries):
        try:
            return scholarly.fill(obj)
        except Exception as e:
            
            sleep_s = base * (1.5 ** t) + random.random() * jitter
            print(f"  warn: fill failed ({type(e).__name__}): {e} | sleeping {sleep_s:.1f}s")
            time.sleep(sleep_s)
    raise RuntimeError("fill_with_backoff: exceeded retries")

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
        if serves_pdf_cached(u):
        # if serves_pdf(u):
            return u
    for u in uniq:
        if is_likely_pdf_url(u):
            return u
    return ""

# ---------- NEW: venue/arXiv inference + duplicate merging helpers ----------

# def infer_publication_string(bib: Dict[str, Any], pub: Dict[str, Any]) -> str:
#     """
#     Prefer explicit venue/journal/booktitle. If none and looks like arXiv, return 'arXiv'.
#     Else ''.
#     """
#     for k in ("journal", "venue", "booktitle"):
#         v = (bib.get(k) or "").strip()
#         if v:
#             return v
#     # Some entries mark arXiv as journal or in URL
#     j = (bib.get("journal") or "").lower()
#     if "arxiv" in j:
#         return "arXiv"
#     for key in ("eprint_url", "pub_url", "url"):
#         u = (pub.get(key) or "").lower()
#         if "arxiv.org" in u:
#             return "arXiv"
#     return ""


# def infer_publication_string(bib: Dict[str, Any], pub: Dict[str, Any]) -> str:
#     """
#     Prefer explicit venue/journal/booktitle.
#     If none found and looks like arXiv, return just 'arXiv' (no ID).
#     """
#     for k in ("journal", "venue", "booktitle"):
#         v = (bib.get(k) or "").strip()
#         if v:
#             return v

#     # Detect arXiv in either the journal field or URL, return clean 'arXiv'
#     j = (bib.get("journal") or "").lower()
#     if "arxiv" in j:
#         return "arXiv"
#     for key in ("eprint_url", "pub_url", "url"):
#         u = (pub.get(key) or "").lower()
#         if "arxiv.org" in u:
#             return "arXiv"
#     return ""


# replace your infer_publication_string with this
def infer_publication_string(bib: Dict[str, Any], pub: Dict[str, Any], pdf_url: str = "") -> str:
    """
    Prefer explicit venue/journal/booktitle (but ignore vague strings).
    If none, and any field or the final pdf_url points to arXiv, return plain 'arXiv'.
    """
    # 1) real venues first
    bad = re.compile(r"(preprint|under review|submitted|manuscript|tech(\s|-)?report)", re.I)
    for k in ("journal", "venue", "booktitle"):
        v = (bib.get(k) or "").strip()
        if v and not bad.search(v):
            return v

    # 2) arXiv detection from any hint
    hay = " ".join([
        (bib.get("journal") or ""),
        (bib.get("eprint") or ""),
        (pub.get("eprint_url") or ""),
        (pub.get("pub_url") or ""),
        (pub.get("url") or ""),
        pdf_url or "",
    ]).lower()
    if "arxiv.org" in hay or "arxiv" in hay:
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
    def __init__(self, title, authors, year, month, day, pdf_url, publication, bib):
        self.title = title
        self.authors = authors
        self.year = year
        self.month = month
        self.day = day
        self.pdf_url = pdf_url
        self.publication = publication
        self.bib = bib

    def richness(self) -> int:
        return info_richness_score(self.bib, self.pdf_url, self.publication)

# ---------------------------------------------------------------------------

# def write_bundle(title: str, authors: List[str], year: int, pdf_url: str, publication: str):
# def write_bundle(title: str, authors: List[str], y: int, m: int, d: int, pdf_url: str, publication: str):

#     date_iso = ymd_to_hugo_iso(y, m, d)
#     """Write Hugo bundle; same structure as yours, now with publication filled."""
#     fm = []
#     fm.append("---")
#     fm.append('title: "{}"'.format(title.replace('"', '\\"')))
#     fm.append("authors:")
#     for a in authors:
#         fm.append('  - "{}"'.format(a.replace('"', '\\"')))
#     date_iso = year_to_iso(year)
#     fm.append(f"date: '{date_iso}'")
#     fm.append(f"publishDate: '{date_iso}'")
#     fm.append("draft: false")
#     fm.append('publication: "{}"'.format(publication.replace('"', '\\"') if publication else ""))
#     fm.append(f'url_pdf: "{pdf_url}"' if pdf_url else 'url_pdf: ""')
#     fm.append("image:")
#     fm.append("  preview_only: true")
#     fm.append("---\n")

#     slug = slugify(f"{title[:80]}-{year}")
#     dst_dir = OUT_DIR / slug
#     dst_dir.mkdir(parents=True, exist_ok=True)
#     dst = dst_dir / "index.md"
#     content = "\n".join(fm)

#     if DRY_RUN:
#         print(f"[DRY_RUN] Would write {dst}:\n{content}")
#     else:
#         dst.write_text(content, encoding="utf-8")
#         print(f"Wrote {dst}")


def write_bundle(title: str, authors: List[str], y: int, m: int, d: int, pdf_url: str, publication: str):
    """Write Hugo bundle; now date supports month (fallback Jan)."""
    date_iso = ymd_to_hugo_iso(y, m, d)

    fm = []
    fm.append("---")
    fm.append('title: "{}"'.format(title.replace('"', '\\"')))
    fm.append("authors:")
    for a in authors:
        fm.append('  - "{}"'.format(a.replace('"', '\\"')))
    fm.append(f"date: '{date_iso}'")
    fm.append(f"publishDate: '{date_iso}'")
    fm.append("draft: false")
    fm.append('publication: "{}"'.format(publication.replace('"', '\\"') if publication else ""))
    fm.append(f'url_pdf: "{pdf_url}"' if pdf_url else 'url_pdf: ""')
    fm.append("image:")
    fm.append("  preview_only: true")
    fm.append("---\n")

    slug = slugify(f"{title[:80]}-{y}")
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
    cached_recs, cached_keys = load_author_cache(scholar_id)
    if cached_recs:
        print(f"Loaded {len(cached_recs)} cached pubs for {scholar_id}")
        out.extend(cached_recs)

    print(f"Fetching author: {scholar_id}")
    author = scholarly.search_author_id(scholar_id)
    if not author:
        print(f"  warn: no author found for {scholar_id} (invalid ID or blocked)")
        return out
    author = scholarly.fill(author, sections=["basics", "publications"])
    pubs = author.get("publications", []) or []
    cur_year = datetime.utcnow().year

    for p in pubs:
        bib0 = p.get("bib", {}) or {}
        raw_title0 = (bib0.get("title") or "").strip()
        title0 = sanitize_text(raw_title0)
        if title0:
            key0 = normalize_title_key(title0)
            if key0 in cached_keys:
                # already cached, skip all network
                continue

        try:
            # p = scholarly.fill(p)
            p = fill_with_backoff(p)
            time.sleep(0.8 + random.random() * 0.6)  # small per-publication jitter
        except Exception as e:
            print(f"  warn: failed to fill a pub for {scholar_id}: {e}")
            continue

        bib = p.get("bib", {}) or {}

        bib = dict(p.get("bib", {}) or {})
        bib.pop("abstract", None)


        raw_title = (bib.get("title") or "").strip()
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

        # y, m, d = resolve_pub_date_ymd(year=yr, pub_obj=p)
        y, m, d = resolve_pub_date_ymd(year=yr, pub_obj=p, bib=bib)

        authors = normalize_authors(bib.get("author"))
        pdf_url = pick_pdf_url(p)

        publication = infer_publication_string(bib, p, pdf_url)  # pass pdf_url here
        if pdf_url:
            print(f"  ✔ PDF: {pdf_url}")
        else:
            print(f"  ✖ No PDF for: {title}")

        # publication = infer_publication_string(bib, p)  # NEW


        rec = PubRecord(
            title=title, authors=authors,
            year=yr, month=m, day=d,
            pdf_url=pdf_url, publication=publication, bib=bib
        )
        out.append(rec)

        # persist immediately so we can resume if blocked mid-run
        append_author_cache(scholar_id, rec)
        cached_keys.add(normalize_title_key(rec.title))


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

    # # Finally, write bundles
    # for rec in merged:
    #     write_bundle(
    #         title=rec.title,
    #         authors=rec.authors,
    #         year=rec.year,
    #         pdf_url=rec.pdf_url,
    #         publication=rec.publication
    #     )
    for rec in merged:
        write_bundle(
            title=rec.title,
            authors=rec.authors,
            y=rec.year,
            m=rec.month,
            d=rec.day,
            pdf_url=rec.pdf_url,
            publication=rec.publication
        )

if __name__ == "__main__":
    main()
