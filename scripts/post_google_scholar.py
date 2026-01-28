#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, Tuple
import shutil

ARXIV_PDF_RE = re.compile(r"https?://arxiv\.org/pdf/(\d{4}\.\d{4,5})(?:v\d+)?\.pdf", re.IGNORECASE)
YEAR_SUFFIX_RE = re.compile(r".*-(\d{4})$")

def extract_year_from_folder(folder_name: str) -> Optional[int]:
    m = YEAR_SUFFIX_RE.match(folder_name)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None

def parse_arxiv_from_url(url: str) -> Optional[Tuple[str, str]]:
    """
    Return (arxiv_id, iso_date) from arxiv pdf url.
    Example: https://arxiv.org/pdf/2506.13992.pdf -> ("2506.13992", "2025-06-01T00:00:00Z")
    """
    m = ARXIV_PDF_RE.match(url.strip())
    if not m:
        return None
    arxiv_id = m.group(1)
    # arXiv id starts with yymm
    yy = int(arxiv_id[0:2])
    mm = int(arxiv_id[2:4])
    yyyy = 2000 + yy  # new-style arXiv ids are 20xx
    iso_date = f"{yyyy:04d}-{mm:02d}-01T00:00:00Z"
    return arxiv_id, iso_date

def strip_bib_braces(s: str) -> str:
    return re.sub(r"[{}]", "", s)

def yaml_set_field(lines: list[str], key: str, value: str) -> list[str]:
    """
    Replace a YAML front matter field like:
      key: '...'
    If not present, insert it before the closing '---' of front matter.
    Assumes file starts with '---' front matter.
    """
    # We will keep your site's style: single quotes
    new_line = f"{key}: '{value}'"

    # Find front matter end
    if not lines or lines[0].strip() != "---":
        return lines  # not a standard front matter file

    fm_end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_end = i
            break
    if fm_end is None:
        return lines

    # Replace if exists in front matter
    pat = re.compile(rf"^{re.escape(key)}\s*:\s*.*$")
    for i in range(1, fm_end):
        if pat.match(lines[i].strip()):
            lines[i] = new_line + "\n"
            return lines

    # Insert before fm_end
    lines.insert(fm_end, new_line + "\n")
    return lines

def yaml_get_field(lines: list[str], key: str) -> Optional[str]:
    """
    Read a simple YAML scalar from front matter: key: "..." or key: '...'
    """
    if not lines or lines[0].strip() != "---":
        return None
    fm_end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_end = i
            break
    if fm_end is None:
        return None

    pat = re.compile(rf"^{re.escape(key)}\s*:\s*(.*)\s*$")
    for i in range(1, fm_end):
        m = pat.match(lines[i].rstrip("\n"))
        if m:
            raw = m.group(1).strip()
            # strip surrounding quotes if present
            if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
                raw = raw[1:-1]
            return raw.strip()
    return None

def strip_title_braces_in_frontmatter(lines: list[str]) -> list[str]:
    """
    Optional: remove {} in title field if present.
    """
    title = yaml_get_field(lines, "title")
    if title is None:
        return lines
    cleaned = strip_bib_braces(title)
    if cleaned != title:
        lines = yaml_set_field(lines, "title", cleaned)
    return lines

def process_index_md(path: Path) -> bool:
    """
    Returns True if file modified.
    """
    text = path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    original = text[:]

    # (2) if no url_pdf, ignore it
    url_pdf = yaml_get_field(text, "url_pdf")
    if not url_pdf:
        return False

    # Optional: clean braces in title
    text = strip_title_braces_in_frontmatter(text)

    arxiv = parse_arxiv_from_url(url_pdf)
    if arxiv:
        arxiv_id, iso_date = arxiv
        # rewrite publication + dates
        text = yaml_set_field(text, "publication", f"arXiv:{arxiv_id}")
        text = yaml_set_field(text, "date", iso_date)
        text = yaml_set_field(text, "publishDate", iso_date)

    if text != original:
        path.write_text("".join(text), encoding="utf-8")
        return True
    return False

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Path to publication folders root (e.g., pub/ or content/publication/)")
    ap.add_argument("--min_year", type=int, default=2023, help="Keep/process only folders with -YEAR >= min_year (default: 2022 means after 2021)")
    ap.add_argument("--out", required=True, help="Output directory for cleaned publication folders")

    args = ap.parse_args()

    root = Path(args.root)
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        raise SystemExit(f"Root not found: {root}")

    modified = 0
    scanned = 0

    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue

        year = extract_year_from_folder(d.name)
        if year is None or year < args.min_year:
            continue  # (1) only after 2022

        src_index = d / "index.md"
        if not src_index.exists():
            continue

        # create output folder
        dst_dir = out_root / d.name
        dst_dir.mkdir(parents=True, exist_ok=True)

        dst_index = dst_dir / "index.md"

        # copy index.md
        shutil.copy2(src_index, dst_index)

        # process copied file
        if process_index_md(dst_index):
            modified += 1

        scanned += 1

    print(f"Scanned {scanned} index.md files (year >= {args.min_year}); modified {modified}.")

if __name__ == "__main__":
    main()
