"""
Determination resolver. Bridges capabilities → aggregator output.

A renderer asks: "Give me the ControlDetermination for Rev 5 control IA-2,
considering all capabilities that satisfy it." This module answers, calling
aggregators as needed and caching their output within a single render.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from aggregators._base import AggregatorRunContext, ControlDetermination
from renderers.shared.capability_loader import Capability


@dataclass
class ResolvedCapabilityEntry:
    """A capability's contribution to ONE control or KSI."""
    capability: Capability
    determination: ControlDetermination | None   # None for declared-mode caps
    declared_statement: str                       # Non-empty for declared caps


class DeterminationResolver:
    """Caches aggregator outputs so each aggregator runs at most once per render."""

    def __init__(self, ctx: AggregatorRunContext):
        self.ctx = ctx
        self._cache: dict[str, list[ControlDetermination]] = {}

    def _run_aggregator(self, cap: Capability) -> list[ControlDetermination]:
        key = cap.aggregator_path
        if key not in self._cache:
            aggregator = cap.load_aggregator()
            self._cache[key] = aggregator.determine(self.ctx)
        return self._cache[key]

    def for_rev5_control(self, control_id: str, caps: Iterable[Capability]) -> list[ResolvedCapabilityEntry]:
        entries: list[ResolvedCapabilityEntry] = []
        for cap in caps:
            if cap.is_aggregator_backed:
                determination = self._find_determination(
                    self._run_aggregator(cap),
                    framework="fedramp_rev5",
                    control_id=control_id,
                )
                entries.append(ResolvedCapabilityEntry(cap, determination, ""))
            else:
                entries.append(ResolvedCapabilityEntry(cap, None, cap.statement))
        return entries

    def for_ksi(self, ksi: str, caps: Iterable[Capability]) -> list[ResolvedCapabilityEntry]:
        entries: list[ResolvedCapabilityEntry] = []
        for cap in caps:
            if cap.is_aggregator_backed:
                determination = self._find_determination(
                    self._run_aggregator(cap),
                    framework="fedramp_20x",
                    control_id=ksi,
                )
                entries.append(ResolvedCapabilityEntry(cap, determination, ""))
            else:
                entries.append(ResolvedCapabilityEntry(cap, None, cap.statement))
        return entries

    @staticmethod
    def _find_determination(
        determinations: list[ControlDetermination],
        framework: str,
        control_id: str,
    ) -> ControlDetermination | None:
        for d in determinations:
            if d.framework == framework and d.control_id == control_id:
                return d
        return None
