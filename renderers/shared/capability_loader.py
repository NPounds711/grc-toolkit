"""
Capability loader. Single entry point for every renderer.

Two flavors of capability:
  aggregator-backed — has `aggregator: aggregators.mfa`. Renderer asks the
      aggregator for live-state-derived determinations at render time.
  declared          — has `capability_statement` prose. Used for placeholders
      that document intent before an aggregator exists, or for capabilities
      whose claim can't be derived from observable state.

Manual controls (process, personnel, physical security) live under
`manual-controls/` and load via a separate path; see manual_controls_loader.
"""

from __future__ import annotations

import datetime
import importlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


class CapabilityValidationError(ValueError):
    pass


@dataclass
class Capability:
    raw: dict[str, Any]

    @property
    def id(self) -> str: return self.raw["id"]
    @property
    def title(self) -> str: return self.raw["title"]

    @property
    def aggregator_path(self) -> str | None:
        return self.raw.get("aggregator")

    @property
    def is_aggregator_backed(self) -> bool:
        return self.aggregator_path is not None

    @property
    def statement(self) -> str:
        """Declared statement. Empty when aggregator-backed."""
        return self.raw.get("capability_statement", "").strip()

    def rev5_controls(self) -> list[dict]:
        return self.raw.get("satisfies", {}).get("fedramp_rev5", [])

    def ksis(self) -> list[dict]:
        return self.raw.get("satisfies", {}).get("fedramp_20x", [])

    def evidence(self) -> list[dict]:
        return self.raw.get("evidence", [])

    def provenance(self) -> dict:
        return self.raw.get("provenance", {})

    def load_aggregator(self):
        """Import the aggregator module and return its instance.
        Returns None if this capability is declared-mode."""
        if not self.is_aggregator_backed:
            return None
        module = importlib.import_module(self.aggregator_path)
        return module.AGGREGATOR


def _validate_aggregator_invariants(cap: Capability, path: Path) -> None:
    """Enforce: aggregator-backed cannot carry capability_statement, and
    its satisfies must be a subset of the aggregator's declared coverage."""
    if not cap.is_aggregator_backed:
        if not cap.statement:
            raise CapabilityValidationError(
                f"{path}: capability without an aggregator must have a "
                f"capability_statement."
            )
        return

    if cap.statement:
        raise CapabilityValidationError(
            f"{path}: aggregator-backed capabilities must not carry a "
            f"capability_statement (the aggregator emits it from live state)."
        )

    aggregator = cap.load_aggregator()
    supported = set(aggregator.SUPPORTED_CONTROLS_REV5)
    declared = {e["control"] for e in cap.rev5_controls()}
    extra = declared - supported
    if extra:
        raise CapabilityValidationError(
            f"{path}: declares Rev 5 controls {sorted(extra)} that are not "
            f"in aggregator {cap.aggregator_path}'s SUPPORTED_CONTROLS_REV5. "
            f"Either add them to the aggregator or remove from this capability."
        )

    supported_ksi = set(aggregator.SUPPORTED_KSIS)
    declared_ksi = {e["ksi"] for e in cap.ksis()}
    extra_ksi = declared_ksi - supported_ksi
    if extra_ksi:
        raise CapabilityValidationError(
            f"{path}: declares KSIs {sorted(extra_ksi)} that are not in "
            f"aggregator {cap.aggregator_path}'s SUPPORTED_KSIS."
        )


def load_all() -> list[Capability]:
    """Load + validate every capability under capabilities/."""
    with open(SCHEMA_PATH) as f:
        schema = yaml.safe_load(f)

    capabilities: list[Capability] = []
    seen_ids: dict[str, Path] = {}

    for yaml_path in sorted(CAPABILITIES_DIR.rglob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue
        with open(yaml_path) as f:
            data = _stringify_dates(yaml.safe_load(f))

        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            raise CapabilityValidationError(
                f"Schema violation in {yaml_path}: {e.message}"
            ) from e

        cap_id = data["id"]
        if cap_id in seen_ids:
            raise CapabilityValidationError(
                f"Duplicate capability id '{cap_id}': "
                f"defined in both {seen_ids[cap_id]} and {yaml_path}"
            )
        seen_ids[cap_id] = yaml_path

        cap = Capability(data)
        _validate_aggregator_invariants(cap, yaml_path)
        capabilities.append(cap)

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
    for cap in caps:
        flavor = "aggregator" if cap.is_aggregator_backed else "declared "
        print(f"  [{flavor}] {cap.id}")
    rev5_idx = index_by_rev5_control(caps)
    ksi_idx = index_by_ksi(caps)
    print(f"\nCovering {len(rev5_idx)} distinct Rev 5 controls and {len(ksi_idx)} KSIs")
