"""
Rev 5 machine-readable renderer — JSON or YAML output.

FedRAMP PMO has stated machine-readable Rev 5 submissions can be in
JSON, YAML, or OSCAL. This renderer covers the first two. The OSCAL
variant lives in renderers/oscal_ssp.py and uses the OSCAL 1.2.0 SSP
schema specifically.

The shape here is intentionally parallel to the 20x FRMR package shape
(renderers/fedramp_20x.py) — same outer envelope, same source-of-evidence
fields per control — so a CSP migrating from Rev 5 → 20x doesn't have to
restructure their downstream tooling. The difference is the inner key:
control implementations are keyed by Rev 5 control IDs (IA-2, IA-2(1),
SC-13, etc.) instead of by KSIs (KSI-IAM-01, ...).

Run:
    python -m renderers.rev5_machine_readable --out samples/rev5.json
    python -m renderers.rev5_machine_readable --out samples/rev5.yaml --format yaml
    python -m renderers.rev5_machine_readable --out samples/rev5.json --fixtures tests/fixtures
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from aggregators._base import AggregatorRunContext
from renderers.shared.capability_loader import (
    Capability,
    index_by_rev5_control,
    load_all,
)
from renderers.shared.determinations import DeterminationResolver, ResolvedCapabilityEntry


CONTROL_FAMILIES = {
    "AC": "Access Control",
    "AT": "Awareness and Training",
    "AU": "Audit and Accountability",
    "CA": "Assessment, Authorization, and Monitoring",
    "CM": "Configuration Management",
    "CP": "Contingency Planning",
    "IA": "Identification and Authentication",
    "IR": "Incident Response",
    "MA": "Maintenance",
    "MP": "Media Protection",
    "PE": "Physical and Environmental Protection",
    "PL": "Planning",
    "PM": "Program Management",
    "PS": "Personnel Security",
    "PT": "Personally Identifiable Information Processing and Transparency",
    "RA": "Risk Assessment",
    "SA": "System and Services Acquisition",
    "SC": "System and Communications Protection",
    "SI": "System and Information Integrity",
    "SR": "Supply Chain Risk Management",
}


def _digital_signature(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _control_family(control_id: str) -> str:
    prefix = re.match(r"^([A-Z]+)", control_id).group(1)
    return CONTROL_FAMILIES.get(prefix, "Unknown")


def _sort_key(control_id: str):
    m = re.match(r"^([A-Z]+)-(\d+)(?:\((\d+)\))?", control_id)
    if not m:
        return (control_id,)
    family, num, enh = m.groups()
    return (family, int(num), int(enh) if enh else 0)


def render(
    csp_name: str = "Example CSP",
    cso_name: str = "Example Cloud Service Offering",
    impact: str = "Moderate",
    fixtures_dir: str | None = None,
    strict_freshness: bool = False,
) -> dict:
    caps = load_all()
    idx = index_by_rev5_control(caps)

    ctx = AggregatorRunContext(
        fixture_mode=bool(fixtures_dir),
        fixture_dir=fixtures_dir or "",
        strict_freshness=strict_freshness,
        run_id=str(uuid.uuid4()),
    )
    resolver = DeterminationResolver(ctx)

    # Group control implementations by control family for readability
    implementations_by_family: dict[str, list[dict]] = {}
    for control_id in sorted(idx.keys(), key=_sort_key):
        entries = resolver.for_rev5_control(control_id, idx[control_id])
        family = _control_family(control_id)
        implementations_by_family.setdefault(family, []).append(
            _render_control(control_id, entries)
        )

    families = [
        {
            "familyName": fam,
            "controlImplementations": impls,
        }
        for fam, impls in sorted(implementations_by_family.items())
    ]

    body = {
        "framework": "FedRAMP Rev 5 (NIST SP 800-53)",
        "schemaVersion": "1.0.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "generator": "grc-toolkit",
        "runId": ctx.run_id,
        "controlFamilies": families,
    }
    body["digitalSignature"] = _digital_signature(body)

    return {
        "package": {
            "cspName": csp_name,
            "cso": cso_name,
            "impact": impact,
            **body,
        }
    }


def _render_control(control_id: str, entries: list[ResolvedCapabilityEntry]) -> dict:
    aggregator_entries = [e for e in entries if e.determination]
    declared_entries = [e for e in entries if not e.determination]

    # Status rollup
    statuses: set[str] = set()
    for e in aggregator_entries:
        statuses.add(e.determination.status)
    for e in declared_entries:
        for ctrl_entry in e.capability.rev5_controls():
            if ctrl_entry["control"] == control_id:
                s = ctrl_entry.get("implementation_status")
                if s:
                    statuses.add(s)
    if "Partially Implemented" in statuses:
        rollup = "Partially Implemented"
    elif "Planned" in statuses or "Inconclusive" in statuses:
        rollup = "Planned"
    elif statuses:
        rollup = "Implemented"
    else:
        rollup = "Not Documented"

    sources: list[dict] = []
    for e in aggregator_entries:
        d = e.determination
        sources.append({
            "capabilityId": e.capability.id,
            "source": "aggregator",
            "aggregator": e.capability.aggregator_path,
            "status": d.status,
            "observedAt": d.observed_at,
            "statement": d.statement,
            "metrics": d.metrics,
            "nonCompliant": d.non_compliant,
            "evidenceRefs": d.evidence_refs,
        })
    for e in declared_entries:
        # Per-control declared status from the YAML entry
        per_ctrl_status = None
        per_ctrl_parts: list[str] = []
        for ctrl_entry in e.capability.rev5_controls():
            if ctrl_entry["control"] == control_id:
                per_ctrl_status = ctrl_entry.get("implementation_status")
                per_ctrl_parts = ctrl_entry.get("parts", [])
        sources.append({
            "capabilityId": e.capability.id,
            "source": "declared",
            "status": per_ctrl_status,
            "parts": per_ctrl_parts,
            "statement": e.declared_statement,
            "evidenceRefs": [ev["id"] for ev in e.capability.evidence()],
        })

    return {
        "controlId": control_id,
        "implementationStatus": rollup,
        "contributingCapabilities": [e.capability.id for e in entries],
        "sources": sources,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--format", choices=["json", "yaml"], default=None,
                    help="Output format. Defaults to file extension (.json or .yaml).")
    ap.add_argument("--csp", default="Example CSP")
    ap.add_argument("--cso", default="Example Cloud Service Offering")
    ap.add_argument("--impact", default="Moderate", choices=["Low", "Moderate", "High"])
    ap.add_argument("--fixtures", default=None)
    ap.add_argument("--strict-freshness", action="store_true")
    args = ap.parse_args()

    fmt = args.format
    if fmt is None:
        suffix = args.out.suffix.lower()
        if suffix in (".yaml", ".yml"):
            fmt = "yaml"
        elif suffix == ".json":
            fmt = "json"
        else:
            ap.error(
                f"Could not infer format from extension '{args.out.suffix}'. "
                "Specify --format json or --format yaml."
            )

    pkg = render(
        args.csp, args.cso, args.impact,
        fixtures_dir=args.fixtures,
        strict_freshness=args.strict_freshness,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        args.out.write_text(json.dumps(pkg, indent=2, default=str))
    else:
        args.out.write_text(yaml.safe_dump(pkg, sort_keys=False, default_flow_style=False))
    print(f"Wrote {args.out} ({fmt.upper()})")


if __name__ == "__main__":
    main()
