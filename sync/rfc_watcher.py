"""
RFC watcher. Scrapes fedramp.gov/rfcs/ for open RFCs and opens a GitHub
issue per RFC the first time it's seen, tagged with the capabilities it
may affect (heuristic keyword match against capability statements + KSI
short codes).

Run:
    python sync/rfc_watcher.py --emit-issues
    python sync/rfc_watcher.py --dry-run   # print what would be opened
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

RFCS_INDEX_URL = "https://www.fedramp.gov/rfcs/"
STATE_FILE = Path(__file__).resolve().parent / ".rfc-state.json"

# Heuristic keyword → KSI category mapping. Used to decide which capabilities
# an RFC might affect. Conservative — false positives are fine; false negatives
# are what we want to avoid.
KEYWORD_AFFECTS = {
    "incident": ["INR", "ICP"],
    "mfa": ["IAM"],
    "authentication": ["IAM"],
    "identity": ["IAM"],
    "encryption": ["SVC"],
    "key management": ["SVC"],
    "logging": ["MLA"],
    "monitoring": ["MLA"],
    "audit": ["MLA"],
    "vulnerability": ["VDR"],
    "supply chain": ["TPR"],
    "recovery": ["RPL"],
    "backup": ["RPL"],
    "change management": ["CMT"],
    "training": ["CED"],
    "policy": ["PIY"],
    "inventory": ["PIY"],
    "boundary": ["CNA"],
    "network": ["CNA"],
}


def fetch_rfc_index() -> list[dict]:
    """Scrape the RFC index. Returns list of {number, title, status, url}.

    Note: the FedRAMP RFC page layout is HTML, not an API. This parser is
    intentionally tolerant — if the layout changes, it logs and exits 0
    rather than failing CI.
    """
    try:
        resp = requests.get(RFCS_INDEX_URL, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Could not fetch {RFCS_INDEX_URL}: {e}", file=sys.stderr)
        return []

    rfcs = []
    # Loose pattern — match "RFC-NNNN" + nearby title text + status hints
    for match in re.finditer(
        r"RFC-(\d{4})[^<]*?<[^>]*>([^<]{5,200})",
        resp.text,
        re.IGNORECASE,
    ):
        number = f"RFC-{match.group(1)}"
        title = match.group(2).strip()
        rfcs.append({
            "number": number,
            "title": title,
            "url": f"{RFCS_INDEX_URL}{number.lower()}/",
        })

    # De-duplicate while preserving order
    seen = set()
    unique = []
    for r in rfcs:
        if r["number"] not in seen:
            seen.add(r["number"])
            unique.append(r)
    return unique


def affected_ksi_categories(text: str) -> set[str]:
    text_lower = text.lower()
    cats = set()
    for keyword, categories in KEYWORD_AFFECTS.items():
        if keyword in text_lower:
            cats.update(categories)
    return cats


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"seen": []}


def save_state(state: dict) -> None:
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def open_issue(rfc: dict, categories: set[str]) -> None:
    title = f"{rfc['number']}: review impact on capabilities"
    body = (
        f"FedRAMP published **{rfc['number']}** — {rfc['title']}\n\n"
        f"Source: {rfc['url']}\n\n"
        f"Heuristic match suggests this may affect capabilities in: "
        f"`{', '.join(sorted(categories)) or 'unknown'}`\n\n"
        "## Action\n\n"
        "1. Read the RFC.\n"
        "2. Identify affected capabilities under `capabilities/`.\n"
        "3. Open a draft PR with proposed updates if the RFC is likely to be adopted.\n"
        "4. Close this issue when the RFC lands in a CR or is withdrawn.\n"
    )
    cmd = [
        "gh", "issue", "create",
        "--title", title,
        "--body", body,
        "--label", "rfc-watch,compliance",
    ]
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-issues", action="store_true",
                    help="Actually open GitHub issues (requires gh CLI).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be opened.")
    args = ap.parse_args()

    state = load_state()
    seen = set(state.get("seen", []))

    rfcs = fetch_rfc_index()
    new = [r for r in rfcs if r["number"] not in seen]

    if not new:
        print("No new RFCs.")
        save_state(state)
        return

    for rfc in new:
        cats = affected_ksi_categories(rfc["title"])
        print(f"NEW: {rfc['number']} — {rfc['title']}  (affects: {sorted(cats) or 'unknown'})")
        if args.emit_issues:
            open_issue(rfc, cats)
        seen.add(rfc["number"])

    if args.emit_issues or not args.dry_run:
        state["seen"] = sorted(seen)
        save_state(state)


if __name__ == "__main__":
    main()
