export SCHOLAR_URLS="https://scholar.google.com/citations?hl=en&user=2LCxkUIAAAAJ&view_op=list_works&sortby=pubdate,https://scholar.google.com/citations?user=hYxTJEcAAAAJ&hl=en,https://scholar.google.com/citations?user=AWNL69MAAAAJ&hl=en,https://scholar.google.com/citations?user=fnE2dSoAAAAJ&hl=en"

export YEAR_FROM=2024          # only fetch publications from 2024+
export OUT_DIR=content/publication
export SLEEP_BETWEEN_AUTHORS=8.0  # safer when using free proxies
export DRY_RUN=0               # set 1 to test without writing files

python scripts/scholar_IPs.py