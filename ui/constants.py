"""Paths shared by the UI modules."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATHS_FILE = ROOT / "paths.local.yaml"
DEFAULT_GENERATE_FILE = ROOT / "generate.local.yaml"
