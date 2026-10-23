"""PartCAD-compatible entry point for the tray with a printed screw joint."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vault.printed_joint import build_printed_box

if "show_object" in globals():
    show_object(build_printed_box())
