"""
Capability loader. Single entry point for every renderer.

Renderers NEVER touch YAML directly. They get pre-validated, indexed
capability objects from here. If the schema changes, only this file
changes — every renderer keeps working.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import datetime

import jsonschema
import yaml


def _stringify_dates(obj):
    """YAML parses 2026-05-15 to datetime.date. Schema wants strings."""
    if isinstance(obj, dict):
        return {k: _stringify_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_stringify_dates(v) for v in obj]
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return obj

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "capabilities" / "_schema.yaml"
CAPABILITIES_DIR = REPO_ROOT / "capabilities"


@dataclass
class Capability:
    raw: dict[str, Any]

    @property
    def id(self) -> str: return self.raw["id"]
    @property
    def title(self) -> str: return self.raw["title"]
    @property
    def statement(self) -> str: return self.raw["capability_statement"].strip()

    def rev5_controls(self) -> list[dict]:
        return self.raw.get("satisfies", {}).get("fedramp_rev5", [])

    def ksis(self) -> list[dict]:
        return self.raw.get("satisfies", {}).get("fedramp_20x", [])

    def evidence(self) -> list[dict]:
        return self.raw.get("evidence", [])

    def provenance(self) -> dict:
        return self.raw.get("provenance", {})


def load_all() -> list[Capability]:
    """Load + validate every capability under capabilities/."""
    with open(SCHEMA_PATH) as f:
        schema = yaml.safe_load(f)

    capabilities = []
    for yaml_path in sorted(CAPABILITIES_DIR.rglob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue
        with open(yaml_path) as f:
            data = _stringify_dates(yaml.safe_load(f))
        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            raise ValueError(f"Schema violation in {yaml_path}: {e.message}") from e
        capabilities.append(Capability(data))
    return capabilities


def index_by_rev5_control(caps: list[Capability]) -> dict[str, list[Capability]]:
    """Map control ID → capabilities that satisfy it. One control may have many."""
    idx: dict[str, list[Capability]] = defaultdict(list)
    for cap in caps:
        for entry in cap.rev5_controls():
            idx[entry["control"]].append(cap)
    return dict(idx)


def index_by_ksi(caps: list[Capability]) -> dict[str, list[Capability]]:
    idx: dict[str, list[Capability]] = defaultdict(list)
    for cap in caps:
        for entry in cap.ksis():
            idx[entry["ksi"]].append(cap)
    return dict(idx)


if __name__ == "__main__":
    caps = load_all()
    print(f"Loaded {len(caps)} capabilities")
    rev5_idx = index_by_rev5_control(caps)
    ksi_idx = index_by_ksi(caps)
    print(f"Covering {len(rev5_idx)} distinct Rev 5 controls and {len(ksi_idx)} KSIs")
    print("\nRev 5 controls covered:")
    for ctrl in sorted(rev5_idx):
        names = [c.id for c in rev5_idx[ctrl]]
        print(f"  {ctrl:12s} ← {', '.join(names)}")
    print("\nKSIs covered:")
    for ksi in sorted(ksi_idx):
        names = [c.id for c in ksi_idx[ksi]]
        print(f"  {ksi:14s} ← {', '.join(names)}")
