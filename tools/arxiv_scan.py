"""
Offline-friendly literature probe.

Victor's competitive claims ("no competitor has masked memory", "nobody tracks
evidence tiers") were written in June 2026 and never re-checked. A claim about
the field that is two months stale is exactly the kind of unverified assertion
Victor exists to flag. This script re-checks them against arXiv directly, so the
answer is reproducible rather than remembered.

    python tools/arxiv_scan.py "agent memory benchmark" "masked retrieval"

Prints date, title, and abstract head for each hit, newest first.
"""
from __future__ import annotations

import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

NS = {"a": "http://www.w3.org/2005/Atom"}
API = "https://export.arxiv.org/api/query"


def build_search(term: str) -> str:
    """
    Multi-word terms are ANDed, not treated as an exact phrase.

    arXiv's `all:"a b c"` is a phrase match, so "memory poisoning agent" returns
    nothing while each word individually is common. Quote a term to force the
    phrase form when that is what you actually want.
    """
    term = term.strip()
    if term.startswith('"') and term.endswith('"'):
        return f"all:{term}"
    words = term.split()
    if len(words) == 1:
        return f'all:"{term}"'
    return " AND ".join(f"all:{w}" for w in words)


def query(term: str, limit: int = 8) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "search_query": build_search(term),
            "start": 0,
            "max_results": limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    req = urllib.request.Request(
        f"{API}?{params}",
        headers={"User-Agent": "victor-arxiv-scan/1.0 (research use)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        root = ET.fromstring(resp.read())

    out = []
    for entry in root.findall("a:entry", NS):
        out.append(
            {
                "date": entry.find("a:published", NS).text[:10],
                "title": " ".join(entry.find("a:title", NS).text.split()),
                "abstract": " ".join(entry.find("a:summary", NS).text.split()),
                "url": entry.find("a:id", NS).text,
            }
        )
    return out


def main(terms: list[str]) -> int:
    for term in terms:
        print(f"\n{'=' * 78}\n  {term}\n{'=' * 78}")
        try:
            hits = query(term)
        except Exception as exc:  # network is the expected failure here
            print(f"  ! {type(exc).__name__}: {exc}")
            continue
        if not hits:
            print("  (no results)")
        for h in hits:
            print(f"\n[{h['date']}] {h['title']}")
            print(f"  {h['url']}")
            print(f"  {h['abstract'][:400]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["agent memory benchmark"]))
