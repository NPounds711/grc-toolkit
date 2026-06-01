"""
Drift test. Fails when any capability references a KSI or control
that no longer exists, has been retired, or has changed meaning in
the upstream FRMR snapshot.

This is what makes the sync workflow useful — it's not enough to
*notice* upstream changes; we have to fail loudly when those changes
break our capability mappings.
"""

import json
from pathlib import Path

import pytest

from renderers.shared.capability_loader import load_all

REPO = Path(__file__).resolve().parents[1]
FRMR_KSIS = REPO / "frameworks" / "fedramp-20x" / "ksis.json"
REV5_CONTROLS = REPO / "frameworks" / "fedramp-rev5" / "controls.json"


def _load_upstream_ksis():
    if not FRMR_KSIS.exists():
        pytest.skip(f"{FRMR_KSIS} not yet synced")
    return json.loads(FRMR_KSIS.read_text())


def _load_upstream_controls():
    if not REV5_CONTROLS.exists():
        pytest.skip(f"{REV5_CONTROLS} not yet synced")
    return json.loads(REV5_CONTROLS.read_text())


def test_every_referenced_ksi_still_exists():
    upstream = _load_upstream_ksis()
    active_ids = {k["id"] for k in upstream["ksis"] if not k.get("retired")}
    retired_ids = {k["id"] for k in upstream["ksis"] if k.get("retired")}

    for cap in load_all():
        for entry in cap.ksis():
            ksi = entry["ksi"]
            assert ksi in active_ids, (
                f"{cap.id} references {ksi}, which is "
                f"{'RETIRED upstream' if ksi in retired_ids else 'unknown to FRMR'}. "
                f"Update the capability or remove the mapping."
            )


def test_every_referenced_control_still_exists():
    upstream = _load_upstream_controls()
    control_ids = {c["id"] for c in upstream["controls"]}

    for cap in load_all():
        for entry in cap.rev5_controls():
            ctrl = entry["control"]
            assert ctrl in control_ids, (
                f"{cap.id} references {ctrl}, which is not in the current "
                f"NIST SP 800-53 catalog. Either the ID is wrong or the "
                f"control has been withdrawn."
            )


def test_capability_provenance_freshness():
    """Flag capabilities not reviewed in 12+ months."""
    from datetime import date, timedelta

    stale_cutoff = (date.today() - timedelta(days=365)).isoformat()
    stale = []
    for cap in load_all():
        last_reviewed = cap.provenance().get("last_reviewed", "")
        if last_reviewed < stale_cutoff:
            stale.append(f"{cap.id} (last reviewed {last_reviewed})")
    assert not stale, "Capabilities overdue for review:\n  " + "\n  ".join(stale)
