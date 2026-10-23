"""PartCAD-compatible entry point for the indexed printed facade screw."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vault.printed_joint import build_printed_screw

if "show_object" in globals():
    show_object(build_printed_screw())
