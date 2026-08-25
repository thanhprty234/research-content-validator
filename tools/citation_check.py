"""Citation quality auditing: URL validity, domain authority, claim alignment.

Deterministic checks (no LLM calls) to flag dead links, low-authority sources,
and unsupported claims before the Critic agent runs.

Gated by env var CITATION_CHECK=0 (default: on).
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ---------------------------------------------------------------------------
# Config / gates
# ---------------------------------------------------------------------------

_ENABLED_ENV = "CITATION_CHECK"
_DEFAULT_TIMEOUT = 5.0
_MAX_URLS = 15
_WORKERS = 8

_AUTHORITY_HIGH = {
    "arxiv.org", "doi.org", "nature.com", "science.org", "ieee.org",
    "acm.org", "wiley.com", "springer.com", "elsevier.com",
    "who.int", "cdc.gov", "nih.gov",
}
_AUTHORITY_MID = {
    "wikipedia.org", "reuters.com", "bbc.com", "apnews.com",
    "github.com", "stackoverflow.com", "medium.com",
}
_SUSPICIOUS_TLDS = {".xyz", ".top", ".work", ".review"}


def enabled() -> bool:
    return os.getenv(_ENABLED_ENV, "1").strip().lower() not in ("0", "false", "no")


# ---------------------------------------------------------------------------
# URL validity
# ---------------------------------------------------------------------------

def _check_single_url(url: str) -> Dict[str, Any]:
    if not url or not url.startswith(("http://", "https://")):
        return {"status": "invalid", "reachable": False}

    try:
        req = Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0 (compatible; rcv-check/1.0)")
        with urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
            code = resp.status
            if 200 <= code < 300:
                return {"status": code, "reachable": True}
            if code == 405:
                pass  # fall through to GET
            elif code in (403, 410, 404):
                return {"status": code, "reachable": False}
            else:
                return {"status": code, "reachable": False}
    except HTTPError as e:
        if e.code == 405:
            pass
        elif e.code in (403, 410, 404):
            return {"status": e.code, "reachable": False}
        else:
            return {"status": e.code, "reachable": False}
    except (URLError, OSError):
        return {"status": None, "reachable": False}

    try:
        req = Request(url, method="GET")
        req.add_header("User-Agent", "Mozilla/5.0 (compatible; rcv-check/1.0)")
        with urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
            resp.read(1)
            return {"status": resp.status, "reachable": True}
    except (HTTPError, URLError, OSError):
        return {"status": None, "reachable": False}


def check_urls(urls: List[str]) -> Dict[str, Dict]:
    seen: set = set()
    unique = []
    for u in urls:
        if u and u not in seen and u.startswith(("http://", "https://")):
            seen.add(u)
            unique.append(u)
    unique = unique[:_MAX_URLS]

    results: Dict[str, Dict] = {}
    with ThreadPoolExecutor(max_workers=min(_WORKERS, len(unique))) as pool:
        futures = {pool.submit(_check_single_url, u): u for u in unique}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                results[url] = fut.result()
            except Exception:
                results[url] = {"status": None, "reachable": False}
    return results


# ---------------------------------------------------------------------------
# Domain authority heuristic
# ---------------------------------------------------------------------------

def _extract_domain(url: str) -> str:
    """Extract effective domain from URL.

    Examples:
        'https://arxiv.org/abs/1234' -> 'arxiv.org'
        'https://cs.stanford.edu/~ando/' -> 'stanford.edu'
        'https://en.wikipedia.org/wiki/Python' -> 'wikipedia.org'
        'https://www.nasa.gov/' -> 'nasa.gov'
    """
    # Match scheme://host portion only (stop at first / : # ?)
    m = re.search(r"https?://([^/:#?]+)", url)
    if not m:
        return ""
    host = m.group(1).lower()
    parts = host.split(".")
    # Return last two segments for proper domain extraction
    # e.g., 'docs.python.org' -> 'python.org', 'cs.stanford.edu' -> 'stanford.edu'
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def domain_authority(url: str) -> int:
    if not url:
        return 0
    domain = _extract_domain(url)
    tld = "." + domain.split(".")[-1] if "." in domain else ""

    for pat in _AUTHORITY_HIGH:
        if pat == domain or domain.endswith("." + pat) or tld == pat:
            return 9
    for pat in _AUTHORITY_MID:
        if pat == domain or domain.endswith("." + pat):
            return 6
    for bad in _SUSPICIOUS_TLDS:
        if tld == bad:
            return 2
    return 4 if url.startswith("https://") else 2


# ---------------------------------------------------------------------------
# Claim-to-source alignment (token-overlap Jaccard, no LLM)
# ---------------------------------------------------------------------------

_STOP = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "because", "but", "and",
    "or", "if", "while", "about", "against", "it", "i", "me", "my",
    "we", "our", "you", "your", "he", "she", "they", "them", "its",
    "this", "that", "these", "those", "which", "who", "whom",
})


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in re.findall(r"\b\w{3,}\b", text)
            if t.lower() not in _STOP]


def claim_alignment(claim: str, evidence: str) -> float:
    if not claim or not evidence:
        return 0.0
    a, b = set(_tokenize(claim)), set(_tokenize(evidence))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

def audit_citations(
    citations: List[Dict],
    key_claims: List[str],
    raw_findings: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Return aggregate citation quality metrics. Never raises."""
    if not enabled():
        return {"enabled": False}

    try:
        urls: List[str] = []
        for c in citations:
            src = c.get("source", "") or ""
            if src and src not in urls:
                urls.append(src)
        if raw_findings:
            for f in raw_findings:
                # Handle both list-of-strings and list-of-dicts shapes
                if isinstance(f, dict):
                    for s in (f.get("sources") or []):
                        if isinstance(s, str) and s not in urls:
                            urls.append(s)
                elif isinstance(f, str) and f not in urls:
                    urls.append(f)

        url_results = check_urls(urls) if urls else {}
        alive = sum(1 for v in url_results.values() if v.get("reachable"))
        dead = sum(1 for v in url_results.values() if not v.get("reachable"))
        avg_auth = (
            sum(domain_authority(u) for u in url_results) / len(url_results)
            if url_results else 0
        )

        alignments: List[Dict] = []
        for claim in key_claims:
            best, best_src = 0.0, ""
            for c in citations:
                score = claim_alignment(claim, c.get("claim_supported", ""))
                if score > best:
                    best, best_src = score, c.get("source", "")
            alignments.append({"claim": claim, "score": round(best, 2), "source": best_src})

        return {
            "enabled": True,
            "total_urls": len(urls),
            "alive_urls": alive,
            "dead_urls": dead,
            "avg_authority": round(avg_auth, 1),
            "alignments": alignments,
            "url_status": url_results,  # needed by critic.py for dead-link flagging
            "low_authority_count": sum(1 for u in url_results if domain_authority(u) < 4),
        }
    except Exception as exc:
        return {
            "enabled": True,
            "error": str(exc),
            "total_urls": 0, "alive_urls": 0, "dead_urls": 0,
            "avg_authority": 0, "alignments": [],
        }
