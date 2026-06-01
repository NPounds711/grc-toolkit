"""
FRMR sync. Pulls the latest FedRAMP machine-readable docs and normalizes
them into the internal schema this toolkit's drift tests expect.

Source:  https://github.com/FedRAMP/docs
Target:  frameworks/fedramp-20x/ksis.json (internal schema)

Internal schema (what drift tests read):

  {
    "frmr_version": "v0.9.0-beta",
    "synced_at": "2026-06-01T06:00:00Z",
    "ksis": [
      { "id": "KSI-IAM-01", "category": "IAM", "name": "...", "retired": false,
        "description": "...", "supersedes": null },
      ...
    ]
  }

Run:
    python sync/frmr_sync.py --target frameworks/fedramp-20x/
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

UPSTREAM_REPO = "https://github.com/FedRAMP/docs.git"

KSI_ID_RE = re.compile(r"^KSI-[A-Z]+-\d+$")


def clone_upstream(workdir: Path) -> Path:
    dest = workdir / "fedramp-docs"
    subprocess.run(
        ["git", "clone", "--depth", "1", UPSTREAM_REPO, str(dest)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return dest


def discover_frmr_files(upstream_dir: Path) -> list[Path]:
    """FedRAMP organizes FRMR docs by process. Walk and pick out KSI files.

    The shape of these JSON files in the upstream repo evolves; this function
    is intentionally permissive — it grabs anything that looks like an FRMR
    JSON and lets parse_ksis() decide whether to use it.
    """
    candidates = []
    for path in upstream_dir.rglob("*.json"):
        if any(seg in path.parts for seg in (".git", "node_modules")):
            continue
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if _looks_like_frmr(data):
            candidates.append(path)
    return candidates


def _looks_like_frmr(data) -> bool:
    """Heuristic: any dict with a 'KSIs' or 'validations' key,
    or a list of items with KSI-style IDs."""
    if isinstance(data, dict):
        if any(k.lower() in ("ksis", "validations", "frmr") for k in data.keys()):
            return True
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and any(
            KSI_ID_RE.match(str(first.get(k, ""))) for k in ("id", "ksiId", "KSI_ID")
        ):
            return True
    return False


def parse_ksis(files: list[Path]) -> list[dict]:
    """Extract canonical KSI entries from heterogeneous FRMR files."""
    out: dict[str, dict] = {}
    for f in files:
        data = json.loads(f.read_text())
        for item in _walk_ksis(data):
            ksi_id = item.get("id") or item.get("ksiId") or item.get("KSI_ID")
            if not ksi_id or not KSI_ID_RE.match(str(ksi_id)):
                continue
            category = ksi_id.split("-")[1]
            entry = {
                "id": ksi_id,
                "category": category,
                "name": item.get("name") or item.get("title") or "",
                "description": item.get("description") or item.get("statement") or "",
                "retired": bool(item.get("retired", False)),
                "supersedes": item.get("supersedes"),
                "superseded_by": item.get("superseded_by"),
                "source_file": str(f.name),
            }
            # Last writer wins (later files may have richer data)
            out[ksi_id] = entry
    return sorted(out.values(), key=lambda x: x["id"])


def _walk_ksis(data):
    """Yield every dict that looks like a KSI entry, anywhere in the tree."""
    if isinstance(data, dict):
        for key in ("id", "ksiId", "KSI_ID"):
            if key in data and KSI_ID_RE.match(str(data[key])):
                yield data
                break
        for v in data.values():
            yield from _walk_ksis(v)
    elif isinstance(data, list):
        for v in data:
            yield from _walk_ksis(v)


def detect_frmr_version(upstream_dir: Path) -> str:
    """Best-effort version detection from common FRMR locations."""
    for candidate in ("CHANGELOG.md", "VERSION", "README.md"):
        path = upstream_dir / candidate
        if not path.exists():
            continue
        text = path.read_text()
        m = re.search(r"v\d+\.\d+\.\d+(?:-[a-z]+)?", text)
        if m:
            return m.group(0)
    return "unknown"


def write_output(target_dir: Path, ksis: list[dict], frmr_version: str) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / "ksis.json"
    payload = {
        "frmr_version": frmr_version,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "source": UPSTREAM_REPO,
        "count": len(ksis),
        "ksis": ksis,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="frameworks/fedramp-20x/", type=Path)
    ap.add_argument(
        "--upstream-dir",
        type=Path,
        default=None,
        help="Use a local clone instead of fetching (handy for offline runs).",
    )
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        upstream = args.upstream_dir or clone_upstream(Path(tmp))
        files = discover_frmr_files(upstream)
        if not files:
            print(
                f"WARNING: no FRMR-shaped JSON files found in {upstream}. "
                "Upstream layout may have changed — inspect manually.",
                file=sys.stderr,
            )
        ksis = parse_ksis(files)
        version = detect_frmr_version(upstream)
        out_path = write_output(args.target, ksis, version)

    print(f"Wrote {out_path} ({len(ksis)} KSIs, FRMR {version})")


if __name__ == "__main__":
    main()
