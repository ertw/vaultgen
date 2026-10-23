"""PartCAD-compatible geometry entry point; publication uses vault.build."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vault.model import build_module
from vault.spec import ModuleSpec

family = "S"
depth_units = 4
height_units = 1

if "show_object" in globals():
    show_object(build_module(spec=ModuleSpec(family, depth_units, height_units)))
