"""Make ``src`` importable when pytest runs from the repository root, and expose sample paths."""

import json
import sys
from pathlib import Path

import pytest
from hypothesis import settings

# Reproducibility: hypothesis draws the same examples on every run.
settings.register_profile("reproducible", derandomize=True, deadline=None)
settings.load_profile("reproducible")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SAMPLES = ROOT / "data" / "samples"


@pytest.fixture
def sample():
    """Load a saved API response by file stem, e.g. ``sample("geocode_kampala")``."""
    def load(stem: str):
        return json.loads((SAMPLES / f"{stem}.json").read_text(encoding="utf-8"))
    return load
