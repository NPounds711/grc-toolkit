"""Pytest configuration. Adds the repo root to sys.path so tests can
import top-level packages (aggregators, connectors, renderers) without
needing to install the project."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
