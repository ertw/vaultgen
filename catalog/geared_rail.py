"""PartCAD-compatible entry point for either native S geared rail."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vault.geared_rails import build_gear_rail

retained = False

if "show_object" in globals():
    show_object(build_gear_rail(retained=retained))
