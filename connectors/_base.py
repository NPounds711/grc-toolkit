"""
Connector base. Connectors are the boundary between this tool and a live
source system (AWS, GCP, Azure, Okta, GitHub, SIEM, ...).

Two responsibilities:
  1. Authenticate (env vars, AWS profile, etc.)
  2. Return raw evidence dicts — no interpretation, no determination logic.

Aggregators consume connectors. Connectors NEVER decide whether something
is compliant. They just say what's true about the system.

Every connector supports fixture mode: if FIXTURE_DIR is set on the
RunContext, the connector reads its data from disk instead of calling APIs.
This is what makes CI runs and demos work without real cloud credentials.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from aggregators._base import AggregatorRunContext


class ConnectorError(RuntimeError):
    pass


class BaseConnector:
    """Common machinery: fixture-mode resolution, credential checks."""

    CONNECTOR_ID: str = "unset"
    FIXTURE_FILES: list[str] = []   # subclasses list expected fixture filenames

    def __init__(self, ctx: AggregatorRunContext):
        self.ctx = ctx

    def fixture(self, name: str) -> Any:
        """Load a fixture JSON file by basename."""
        if not self.ctx.fixture_mode:
            raise ConnectorError(
                f"{self.CONNECTOR_ID}: fixture() called outside fixture mode."
            )
        if not self.ctx.fixture_dir:
            raise ConnectorError(
                f"{self.CONNECTOR_ID}: fixture_mode=True but fixture_dir is empty."
            )
        path = Path(self.ctx.fixture_dir) / self.CONNECTOR_ID / name
        if not path.exists():
            raise ConnectorError(
                f"{self.CONNECTOR_ID}: fixture not found at {path}. "
                f"Expected one of: {self.FIXTURE_FILES}"
            )
        return json.loads(path.read_text())

    @staticmethod
    def env_required(*names: str) -> dict[str, str]:
        """Pull required env vars or raise a clear error."""
        missing = [n for n in names if not os.environ.get(n)]
        if missing:
            raise ConnectorError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Either set them or run with fixture_mode=True."
            )
        return {n: os.environ[n] for n in names}
