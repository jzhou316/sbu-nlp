#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12
}

# ----------------------------
# BibTeX parsing (no deps)
# ----------------------------
def parse_bibtex_entries(text: str) -> List[Dict[str, str]]:
    """
    Minimal BibTeX parser good enough for DBLP BibTeX.
    Returns list of entries; each entry is a dict with keys:
      - ENTRYTYPE, ID, and bib fields (lowercased)
    """
    entries: List[Dict[str, str]] = []
    i = 0
    n = len(text)

    while True:
        m = re.search(r'@(\w+)\s*{\s*([^,]+)\s*,', text[i:], flags=re.S)
        if not m:
            break

        etype, key = m.group(1), m.group(2).strip()
        start = i + m.end()

        # Find matching closing brace of the whole entry
        brace_level = 1
        j = start
        while j < n and brace_level > 0:
            if text[j] == "{":
                brace_level += 1
            elif text[j] == "}":
                brace_level -= 1
            j += 1

        body = text[start:j-1].strip()

        entry: Dict[str, str] = {"ENTRYTYPE": etype.lower(), "ID": key}

        k = 0
        while k < len(body):
            while k < len(body) and body[k] in " \r\n\t,":
                k += 1
            if k >= len(body):
                break

            fm = re.match(r'([A-Za-z][A-Za-z0-9_-]*)\s*=\s*', body[k:])
            if not fm:
                break
            fname = fm.group(1).lower()
            k += fm.end()

            if k >= len(body):
                break

            if body[k] == "{":
                lvl = 1
                vstart = k + 1
                k += 1
                while k < len(body) and lvl > 0:
                    if body[k] == "{":
                        lvl += 1
                    elif body[k] == "}":
                        lvl -= 1
                    k += 1
                val = body[vstart:k-1]
            elif body[k] == '"':
                vstart = k + 1
                k += 1
                while k < len(body) and body[k] != '"':
                    if body[k] == "\\" and k + 1 < len(body):
                        k += 2
                    else:
                        k += 1
                val = body[vstart:k]
                k += 1
            else:
                vstart = k
                while k < len(body) and body[k] not in ",\n\r":
                    k += 1
                val = body[vstart:k].strip()

            val = re.sub(r"\s+", " ", val).strip()
            entry[fname] = val

        entries.append(entry)
        i = j

    return entries


# ----------------------------
# Helpers
# ----------------------------
def norm_title(t: str) -> str:
    t = t.lower()
    t = re.sub(r"[{}]", "", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def title_first_n_words(title: str, n: int = 4) -> str:
    t = title.lower()
    t = re.sub(r"[{}]", "", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    words = t.split()
    return " ".join(words[:n])

def split_authors(author_field: str) -> List[str]:
    return [p.strip() for p in author_field.split(" and ") if p.strip()]

def extract_arxiv_id(e: Dict[str, str]) -> Optional[str]:
    if e.get("eprinttype", "").lower() == "arxiv":
        return e.get("eprint")

    if e.get("journal", "").lower() == "corr":
        if e.get("eprint"):
            return e.get("eprint")
        vol = e.get("volume", "")
        m = re.search(r"abs/(\d{4}\.\d{4,5})", vol)
        if m:
            return m.group(1)

    url = e.get("url", "")
    m = re.search(r"arXiv\.(\d{4}\.\d{4,5})", url)
    if m:
        return m.group(1)

    return None

def is_corr_arxiv(e: Dict[str, str]) -> bool:
    return (e.get("journal", "").lower() == "corr") or (e.get("eprinttype", "").lower() == "arxiv")

def is_non_arxiv_pub(e: Dict[str, str]) -> bool:
    # conference (booktitle) or journal that is not CoRR
    if e.get("booktitle"):
        return True
    j = e.get("journal", "")
    return bool(j) and j.lower() != "corr"

def venue_short(e: Dict[str, str]) -> str:
    bt = e.get("booktitle", "")
    if bt:
        m = re.search(r"\{([A-Za-z0-9\-]+)\}\s*(\d{4})", bt)
        if m:
            return m.group(1)
        return bt.split(",")[0].strip()[:60]

    j = e.get("journal", "")
    if j:
        if j.lower() == "corr":
            return "arXiv"
        return j

    return e.get("ENTRYTYPE", "publication")

def publication_data(e: Dict[str, str]) -> str:
    parts: List[str] = []
    if e.get("booktitle"):
        parts.append(e["booktitle"])
    elif e.get("journal"):
        j = e["journal"]
        vol = e.get("volume")
        if vol:
            j += f" {vol}"
        parts.append(j)

    if e.get("pages"):
        parts.append(f"pp. {e['pages']}")

    return ", ".join(parts).strip()

def pick_pdf_url(e: Dict[str, str], arxiv_id: Optional[str]) -> Optional[str]:
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    url = e.get("url", "")
    if url.lower().endswith(".pdf"):
        return url

    doi = e.get("doi")
    if doi:
        return f"https://doi.org/{doi}"

    return url or None

def extract_date_iso(e: Dict[str, str], arxiv_id: Optional[str]) -> str:
    year = int(e.get("year", "1900"))

    if arxiv_id:
        m = re.match(r"(\d{2})(\d{2})\.\d+", arxiv_id)
        if m:
            yy = int(m.group(1))
            mm = int(m.group(2))
            yyyy = 2000 + yy if yy < 90 else 1900 + yy
            return f"{yyyy:04d}-{mm:02d}-01T00:00:00Z"
        return f"{year:04d}-01-01T00:00:00Z"

    bt = e.get("booktitle", "")
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})", bt)
    if m:
        month = MONTHS[m.group(1)]
        day = int(m.group(2))
        return f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"

    return f"{year:04d}-01-01T00:00:00Z"


# ----------------------------
# Dedup (two-stage)
# ----------------------------
def dedup_stage1_by_norm_title(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Stage 1:
      - group by normalized title
      - if conf/journal (non-CoRR) exists, keep that over arXiv/CoRR
      - otherwise keep the first one
    Also drops entries missing author or title.
    """
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for e in entries:
        title = (e.get("title") or "").strip()
        author = (e.get("author") or "").strip()
        if not title or not author:
            continue
        grouped.setdefault(norm_title(title), []).append(e)

    kept: List[Dict[str, str]] = []
    for _, group in grouped.items():
        # prefer non-arxiv pubs
        non_arxiv = [g for g in group if is_non_arxiv_pub(g)]
        if non_arxiv:
            kept.append(non_arxiv[0])  # keep first non-arxiv
        else:
            kept.append(group[0])      # all arxiv/corr, keep first for now
    return kept

def dedup_stage2_by_title5_and_pubdata(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Stage 2 (your rule):
      - if first 5 words match AND publication_data matches:
          * if one non-arxiv and one arxiv => keep non-arxiv
          * if both arxiv => ignore the first (keep later)
          * if both non-arxiv => keep first
    """
    kept: List[Dict[str, str]] = []
    seen: Dict[Tuple[str, str], int] = {}  # (title5, pubdata) -> index in kept

    for e in entries:
        title = (e.get("title") or "").strip()
        author = (e.get("author") or "").strip()
        if not title or not author:
            continue

        key = (title_first_n_words(title, 5), publication_data(e))
        if key not in seen:
            seen[key] = len(kept)
            kept.append(e)
            continue

        prev_idx = seen[key]
        prev = kept[prev_idx]

        prev_arxiv = is_corr_arxiv(prev)
        curr_arxiv = is_corr_arxiv(e)
        prev_non = is_non_arxiv_pub(prev)
        curr_non = is_non_arxiv_pub(e)

        if prev_non and curr_arxiv:
            continue
        if curr_non and prev_arxiv:
            kept[prev_idx] = e
            continue

        if prev_arxiv and curr_arxiv:
            # ignore the first one => replace with later
            kept[prev_idx] = e
            continue

        # otherwise keep first
        continue

    return kept

def dedup_entries(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    entries = dedup_stage1_by_norm_title(entries)
    entries = dedup_stage2_by_title5_and_pubdata(entries)

    # sort newest first
    def sort_key(e: Dict[str, str]) -> str:
        arx = extract_arxiv_id(e)
        return extract_date_iso(e, arx)

    entries.sort(key=sort_key, reverse=True)
    return entries


# ----------------------------
# Hugo writer
# ----------------------------
def slugify(title: str, year: str, max_len: int = 80) -> str:
    s = title.lower()
    s = s.replace("&", "and")
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if len(s) > max_len:
        parts = s.split("-")
        out = []
        total = 0
        for p in parts:
            if not p:
                continue
            add = len(p) + (1 if out else 0)
            if total + add > max_len:
                break
            out.append(p)
            total += add
        s = "-".join(out) if out else s[:max_len].rstrip("-")
    return f"{s}-{year}"

def to_index_md(
    title: str,
    authors: List[str],
    date_iso: str,
    publication: str,
    url_pdf: Optional[str],
) -> str:
    lines: List[str] = []
    lines.append("---")
    lines.append(f'title: "{title}"')
    lines.append("authors:")
    for a in authors:
        lines.append(f'  - "{a}"')
    lines.append(f"date: '{date_iso}'")
    lines.append(f"publishDate: '{date_iso}'")
    lines.append("draft: false")
    lines.append(f'publication: "{publication}"')
    if url_pdf:
        lines.append(f'url_pdf: "{url_pdf}"')
    lines.append("image:")
    lines.append("  preview_only: true")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bib", type=str, required=True, help="Path to .bib file (downloaded from DBLP)")
    ap.add_argument("--out", type=str, required=True, help="Path to content/publication directory")
    ap.add_argument("--min_year", type=int, default=2022, help="Keep publications with year >= min_year")
    args = ap.parse_args()

    bib_path = Path(args.bib)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    text = bib_path.read_text(encoding="utf-8", errors="ignore")
    raw_entries = parse_bibtex_entries(text)

    # Two-stage dedup + author-required
    entries = dedup_entries(raw_entries)

    # Keep only after min_year
    final_entries: List[Dict[str, str]] = []
    for e in entries:
        y = int(e.get("year", "0"))
        if y >= args.min_year:
            # author already checked in dedup stages, but keep safe:
            if (e.get("author") or "").strip():
                final_entries.append(e)

    # write
    for e in final_entries:
        title = (e.get("title") or "").strip()
        if not title:
            continue

        year = e.get("year", "1900").strip()
        arx = extract_arxiv_id(e)

        if arx and not is_non_arxiv_pub(e):
            publication = f"arXiv:{arx}"
        else:
            publication = venue_short(e)

        date_iso = extract_date_iso(e, arx)
        authors = split_authors(e.get("author", ""))
        if not authors:
            continue  # (1) no author => ignore

        url_pdf = pick_pdf_url(e, arx)

        slug = slugify(title, year)
        pub_folder = out_dir / slug
        pub_folder.mkdir(parents=True, exist_ok=True)

        index_md = to_index_md(
            title=title,
            authors=authors,
            date_iso=date_iso,
            publication=publication,
            url_pdf=url_pdf,
        )
        (pub_folder / "index.md").write_text(index_md, encoding="utf-8")

    print(f"Done. Wrote {len(final_entries)} publication folders into: {out_dir}")


if __name__ == "__main__":
    main()
