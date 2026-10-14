"""Legacy entry point for exporting the current XMind vector preview."""

from pathlib import Path
from runpy import run_path


if __name__ == "__main__":
    run_path(str(Path(__file__).with_name("render_classification_diagram.py")), run_name="__main__")
