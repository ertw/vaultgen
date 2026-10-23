"""PartCAD-compatible geometry entry point; publication uses vault.build."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vault.box import build_box

if "show_object" in globals():
    show_object(build_box())
