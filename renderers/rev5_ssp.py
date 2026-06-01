"""
Rev 5 SSP renderer.

Reads capabilities and produces a Word document with control-implementation
statements in the format FedRAMP Rev 5 SSPs use. Multiple capabilities can
roll up under one control — they get concatenated cleanly.

Run:  python -m renderers.rev5_ssp --out samples/rev5_ssp_fragment.docx \\
            --controls IA-2,IA-2\\(1\\),AC-2,AC-6
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.shared import Inches, Pt, RGBColor

from renderers.shared.capability_loader import (
    Capability,
    index_by_rev5_control,
    load_all,
)

# Rev 5 control families and their full names — synced from NIST SP 800-53r5.
# In production this comes from frameworks/fedramp-rev5/controls.json which
# is itself synced from NIST/OSCAL-content nightly.
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


def _control_family(control_id: str) -> str:
    """IA-2(1) -> 'Identification and Authentication'."""
    prefix = re.match(r"^([A-Z]+)", control_id).group(1)
    return CONTROL_FAMILIES.get(prefix, "Unknown")


def _rollup_status(entries: list[dict]) -> str:
    """If any capability is Partially Implemented, the control is Partial."""
    statuses = {e.get("implementation_status", "Implemented") for e in entries}
    if "Planned" in statuses:
        return "Planned"
    if "Partially Implemented" in statuses:
        return "Partially Implemented"
    if "Alternative" in statuses:
        return "Alternative"
    return "Implemented"


def render(
    output_path: Path,
    requested_controls: list[str] | None = None,
) -> Path:
    caps = load_all()
    idx = index_by_rev5_control(caps)

    if requested_controls:
        idx = {c: caps for c, caps in idx.items() if c in requested_controls}

    doc = Document()

    # ---- Document defaults ----
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(11)

    # ---- Title ----
    title = doc.add_heading("System Security Plan — Control Implementation Statements", 0)
    for run in title.runs:
        run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)

    p = doc.add_paragraph()
    p.add_run(
        "Generated from canonical capability definitions. Do not edit this "
        "document directly — modify the source capability YAML and regenerate. "
        "See provenance section under each control for source attribution."
    ).italic = True

    # Group controls by family for readability
    by_family: dict[str, list[str]] = {}
    for ctrl in sorted(idx.keys(), key=_sort_key):
        family = _control_family(ctrl)
        by_family.setdefault(family, []).append(ctrl)

    for family in sorted(by_family.keys()):
        doc.add_heading(family, level=1)

        for control_id in by_family[family]:
            entries_for_control = []
            for cap in idx[control_id]:
                for e in cap.rev5_controls():
                    if e["control"] == control_id:
                        entries_for_control.append((cap, e))

            _render_control(doc, control_id, entries_for_control)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    return output_path


def _sort_key(control_id: str):
    """Sort AC-2 before AC-2(1) before AC-6."""
    m = re.match(r"^([A-Z]+)-(\d+)(?:\((\d+)\))?", control_id)
    if not m:
        return (control_id,)
    family, num, enh = m.groups()
    return (family, int(num), int(enh) if enh else 0)


def _render_control(doc, control_id: str, entries: list[tuple[Capability, dict]]):
    """Render one control's section. Multiple capabilities concatenate."""
    doc.add_heading(control_id, level=2)

    # Status table
    status = _rollup_status([e for _, e in entries])
    contributing = sorted({cap.id for cap, _ in entries})

    table = doc.add_table(rows=2, cols=2)
    table.style = "Light Grid Accent 1"
    table.cell(0, 0).text = "Implementation Status"
    table.cell(0, 1).text = status
    table.cell(1, 0).text = "Contributing Capabilities"
    table.cell(1, 1).text = ", ".join(contributing)
    for row in table.rows:
        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            for para in cell.paragraphs:
                para.runs[0].font.size = Pt(10) if para.runs else None

    # If any entry specifies parts, list them with the statement (no repetition)
    parted_entries = [(cap, e) for cap, e in entries if e.get("parts")]

    if parted_entries:
        for cap, entry in parted_entries:
            parts = entry.get("parts", [])
            parts_label = (
                f"Addresses part {parts[0]}" if len(parts) == 1
                else f"Addresses parts {', '.join(parts)}"
            )
            doc.add_heading(f"{cap.id}", level=3)
            p = doc.add_paragraph()
            p.add_run(parts_label).bold = True
            doc.add_paragraph(cap.statement)

        # Capabilities without parts on same control
        unparted = [(cap, e) for cap, e in entries if not e.get("parts")]
        for cap, _ in unparted:
            doc.add_heading(f"{cap.id}", level=3)
            doc.add_paragraph(cap.statement)
    else:
        for cap, _ in entries:
            doc.add_heading(f"{cap.id}", level=3)
            doc.add_paragraph(cap.statement)

    # Evidence section
    doc.add_heading("Validation Evidence", level=3)
    for cap, _ in entries:
        for ev in cap.evidence():
            p = doc.add_paragraph(style="List Bullet")
            run = p.add_run(f"{ev['id']}")
            run.bold = True
            p.add_run(
                f" — {ev['type']} from {ev['source']}, "
                f"{ev.get('schedule', 'on-demand')}, "
                f"{ev.get('validation_method', 'automated')}"
            )

    # Provenance
    doc.add_heading("Provenance", level=3)
    provs = {cap.id: cap.provenance() for cap, _ in entries}
    for cap_id, prov in provs.items():
        bits = [f"FRMR: {prov.get('frmr_version', 'n/a')}",
                f"last reviewed {prov.get('last_reviewed', 'n/a')}"]
        for assessment in prov.get("validated_in_assessment", []):
            bits.append(f"validated in {assessment['csp']}/{assessment['assessor_3pao']} ({assessment['date']})")
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(f"{cap_id}: ").bold = True
        p.add_run("; ".join(bits))

    doc.add_paragraph()  # spacer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--controls", default=None,
                    help="Comma-separated list of controls; default = all that have capabilities")
    args = ap.parse_args()

    controls = [c.strip() for c in args.controls.split(",")] if args.controls else None
    out = render(args.out, controls)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
