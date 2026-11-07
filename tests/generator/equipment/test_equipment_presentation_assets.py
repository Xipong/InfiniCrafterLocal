"""Native registration assets are transparent carriers, never recipe artwork."""
from suite_paths import REPO_ROOT
from pathlib import Path
import subprocess
import sys

from PIL import Image

ROOT = REPO_ROOT


def test_equipment_carriers_are_reproducible_native_sized_and_fully_transparent():
    subprocess.run([sys.executable, str(ROOT / "tools/generate/generate_equipment_carriers.py"), "--check"], check=True, timeout=15)
    for suffix, expected in {
        "Head": (40, 1120), "Body": (360, 224), "Legs": (40, 1120),
        "FemaleBody": (40, 1120), "Arms": (40, 1120),
    }.items():
        with Image.open(ROOT / "mod/InfiniCrafterLocal/Assets" / f"GeneratedItem_{suffix}.png") as image:
            assert image.mode == "RGBA"
            assert image.size == expected
            assert image.getchannel("A").getextrema() == (0, 0)
            assert image.getbbox() is None
