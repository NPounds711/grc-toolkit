"""
Generate dynamic docs pages (capabilities.md, coverage.md) from the
canonical capability YAMLs. Runs in CI before `mkdocs build`.

Run:
    python scripts/build_docs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from renderers.shared.capability_loader import (  # noqa: E402
    index_by_ksi,
    index_by_rev5_control,
    load_all,
)

DOCS = REPO / "docs"


def build_capabilities_page() -> str:
    caps = load_all()
    lines = [
        "# Capabilities catalog",
        "",
        "Every capability in this repo, with its cross-framework mappings.",
        "Edit the source YAML under `capabilities/` to update an entry.",
        "",
    ]
    for cap in sorted(caps, key=lambda c: c.id):
        lines.append(f"## {cap.title}")
        lines.append(f"`{cap.id}`")
        lines.append("")
        lines.append(cap.statement)
        lines.append("")
        lines.append("### Satisfies")
        lines.append("")

        ksis = cap.ksis()
        if ksis:
            lines.append("**FedRAMP 20x**")
            lines.append("")
            lines.append("| KSI | Coverage | Notes |")
            lines.append("|---|---|---|")
            for entry in ksis:
                lines.append(
                    f"| `{entry['ksi']}` | "
                    f"{entry.get('coverage', '—')} | "
                    f"{entry.get('notes', '').splitlines()[0] if entry.get('notes') else ''} |"
                )
            lines.append("")

        rev5 = cap.rev5_controls()
        if rev5:
            lines.append("**FedRAMP Rev 5 (NIST SP 800-53)**")
            lines.append("")
            lines.append("| Control | Coverage | Parts | Status |")
            lines.append("|---|---|---|---|")
            for entry in rev5:
                parts = ", ".join(entry.get("parts", [])) or "—"
                lines.append(
                    f"| `{entry['control']}` | "
                    f"{entry.get('coverage', '—')} | "
                    f"{parts} | "
                    f"{entry.get('implementation_status', '—')} |"
                )
            lines.append("")

        ev = cap.evidence()
        if ev:
            lines.append("### Evidence")
            lines.append("")
            lines.append("| ID | Type | Source | Schedule | Method |")
            lines.append("|---|---|---|---|---|")
            for e in ev:
                lines.append(
                    f"| `{e['id']}` | "
                    f"{e['type']} | "
                    f"{e['source']} | "
                    f"{e.get('schedule', '—')} | "
                    f"{e.get('validation_method', '—')} |"
                )
            lines.append("")

        prov = cap.provenance()
        lines.append("### Provenance")
        lines.append("")
        lines.append(f"- Last reviewed: **{prov.get('last_reviewed', 'n/a')}**")
        lines.append(f"- FRMR version: `{prov.get('frmr_version', 'n/a')}`")
        for assessment in prov.get("validated_in_assessment", []):
            lines.append(
                f"- Validated in **{assessment['csp']}** / "
                f"**{assessment['assessor_3pao']}** "
                f"({assessment['date']}) — "
                f"[submission]({assessment['url']})"
            )
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def build_coverage_page() -> str:
    caps = load_all()
    ksi_idx = index_by_ksi(caps)
    ctrl_idx = index_by_rev5_control(caps)

    lines = [
        "# Coverage matrix",
        "",
        "Which FedRAMP 20x KSIs and Rev 5 controls currently have capability "
        "mappings in this repo.",
        "",
        "## FedRAMP 20x KSIs covered",
        "",
        f"**{len(ksi_idx)}** distinct KSIs covered by **{len(caps)}** capabilities.",
        "",
        "| KSI | Contributing capabilities |",
        "|---|---|",
    ]
    for ksi in sorted(ksi_idx):
        names = ", ".join(f"`{c.id}`" for c in ksi_idx[ksi])
        lines.append(f"| `{ksi}` | {names} |")

    lines.extend(
        [
            "",
            "## FedRAMP Rev 5 controls covered",
            "",
            f"**{len(ctrl_idx)}** distinct controls covered.",
            "",
            "| Control | Contributing capabilities |",
            "|---|---|",
        ]
    )
    for ctrl in sorted(ctrl_idx):
        names = ", ".join(f"`{c.id}`" for c in ctrl_idx[ctrl])
        lines.append(f"| `{ctrl}` | {names} |")

    lines.extend(
        [
            "",
            "## What's not covered",
            "",
            "When `frameworks/fedramp-20x/ksis.json` is populated by the sync "
            "workflow, this page will also list KSIs that exist upstream but "
            "have no capability mapping yet — those are the gaps to prioritize.",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    (DOCS / "capabilities.md").write_text(build_capabilities_page() + "\n")
    (DOCS / "coverage.md").write_text(build_coverage_page() + "\n")
    print("Wrote docs/capabilities.md and docs/coverage.md")


if __name__ == "__main__":
    main()
