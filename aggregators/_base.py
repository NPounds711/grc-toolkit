"""
Aggregator base class. Every aggregator under aggregators/ subclasses this.

An aggregator is a deterministic Python module that:

  1. Knows which controls (Rev 5 + 20x + SOC 2 + CSF) it can determine.
  2. Knows which connectors to call to get raw evidence.
  3. Applies deterministic rules to the evidence to produce an
     ImplementationDetermination per control.

The capability YAML pointing at this aggregator is a thin manifest.
The aggregator IS the source of truth for which controls it covers
and what "implemented" means for each of them.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol


Status = Literal[
    "Implemented",
    "Partially Implemented",
    "Planned",
    "Alternative Implementation",
    "Not Applicable",
    "Inconclusive",
]


@dataclass
class ControlDetermination:
    """Per-control verdict produced by an aggregator.

    This is what renderers consume — they no longer read prose from a YAML.
    They read this object and emit it in whatever shape the target format
    requires (Word doc, FRMR JSON, OSCAL, etc.)."""

    control_id: str                    # e.g., "IA-2(1)" or "KSI-IAM-01"
    framework: str                     # "fedramp_rev5" | "fedramp_20x" | "soc2" | "nist_csf_2"
    status: Status
    observed_at: str                   # ISO 8601 UTC
    statement: str                     # Auto-generated implementation narrative
    evidence_refs: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    non_compliant: list[Any] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AggregatorRunContext:
    """Everything an aggregator needs to know about how it's being invoked.

    Renderers create one of these and pass it to aggregator.determine().
    Different render contexts may produce different determinations (e.g.,
    a 'preview' render might be permissive about missing evidence).
    """
    fixture_mode: bool = False          # Read fixtures instead of calling APIs
    fixture_dir: str = ""               # Where the fixtures live
    strict_freshness: bool = False      # Fail if evidence is stale
    run_id: str = ""                    # Carried into Finding documents


class AggregatorProtocol(Protocol):
    """Structural protocol every aggregator satisfies. Loader uses these
    fields to validate capability YAMLs."""

    AGGREGATOR_ID: str
    SUPPORTED_CONTROLS_REV5: list[str]
    SUPPORTED_KSIS: list[str]
    SUPPORTED_SOC2: list[str]
    SUPPORTED_CSF2: list[str]

    def determine(self, ctx: AggregatorRunContext) -> list[ControlDetermination]:
        ...


class BaseAggregator:
    """Concrete base providing a no-op skeleton. Real aggregators override
    SUPPORTED_* lists and implement determine()."""

    AGGREGATOR_ID: str = "unset"
    SUPPORTED_CONTROLS_REV5: list[str] = []
    SUPPORTED_KSIS: list[str] = []
    SUPPORTED_SOC2: list[str] = []
    SUPPORTED_CSF2: list[str] = []

    def determine(self, ctx: AggregatorRunContext) -> list[ControlDetermination]:
        raise NotImplementedError(
            f"{self.AGGREGATOR_ID}: determine() must be implemented."
        )

    # ---- helpers shared by concrete aggregators ----

    @staticmethod
    def now_utc() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    @staticmethod
    def status_from_percentage(pct: float, full: float = 100.0, partial: float = 95.0) -> Status:
        if pct >= full:
            return "Implemented"
        if pct >= partial:
            return "Partially Implemented"
        return "Planned"
