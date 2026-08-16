"""Put the repo root (where the flat modules live) on sys.path for the test suite."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
