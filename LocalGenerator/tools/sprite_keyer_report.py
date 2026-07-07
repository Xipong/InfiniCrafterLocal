from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache" / "sprites"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep import-side config deterministic for this diagnostic tool.
os.environ.setdefault("INFINI_SAVE_SPRITE_STAGES", "1")
os.environ.setdefault("INFINI_BG_REMOVE_MODE", "sprite_keyer")
os.environ.setdefault("INFINI_SPRITE_PROCESSING_PROFILE", "master_soft")

spec = importlib.util.spec_from_file_location("infini_server", ROOT / "server.py")
if spec is None or spec.loader is None:
    raise SystemExit("Could not import LocalGenerator/server.py")
server = importlib.util.module_from_spec(spec)
sys.modules["infini_server"] = server
spec.loader.exec_module(server)  # type: ignore[union-attr]
Image = server.Image


def checker(size: tuple[int, int], cell: int = 8):
    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    px = img.load()
    a = (208, 208, 208, 255)
    b = (112, 112, 112, 255)
    for y in range(h):
        for x in range(w):
            px[x, y] = a if ((x // cell + y // cell) % 2 == 0) else b
    return img


def composite_on(img, bg):
    img = img.convert("RGBA")
    if isinstance(bg, tuple):
        base = Image.new("RGBA", img.size, bg)
    else:
        base = bg.convert("RGBA").resize(img.size)
    base.alpha_composite(img)
    return base


def alpha_mask(img):
    a = img.convert("RGBA").getchannel("A")
    return Image.merge("RGBA", (a, a, a, Image.new("L", a.size, 255)))


def label_bar(text: str, width: int, height: int = 18):
    # No font dependency: just make a dark separator; filename carries labels.
    return Image.new("RGBA", (width, height), (24, 24, 24, 255))


def build_montage(raw_path: Path, final_path: Path, out_path: Path):
    raw = Image.open(raw_path).convert("RGBA")
    final = Image.open(final_path).convert("RGBA")
    tile = 128
    views = []
    for im in [raw, final, composite_on(final, checker(final.size, 4)), composite_on(final, (34, 34, 34, 255)), composite_on(final, (226, 226, 226, 255)), alpha_mask(final)]:
        views.append(im.resize((tile, tile), Image.Resampling.NEAREST))
    out = Image.new("RGBA", (tile * len(views), tile), (16, 16, 16, 255))
    for i, im in enumerate(views):
        out.alpha_composite(im, (i * tile, 0))
    out.save(out_path)


def latest_raws(limit: int = 8) -> list[Path]:
    if not CACHE.exists():
        return []
    patterns = ["*_raw_sdcpp_server_0.png", "*_raw_a1111_0.png", "*_raw_comfy_0.png"]
    files: list[Path] = []
    for pat in patterns:
        files.extend(CACHE.glob(pat))
    files = sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def main() -> None:
    ap = argparse.ArgumentParser(description="Run InfiniCrafter sprite_keyer postprocess diagnostics on raw generated PNGs.")
    ap.add_argument("paths", nargs="*", help="Raw PNG paths. If omitted, scans cache/sprites for latest raw generated images.")
    ap.add_argument("--role", default="item", choices=["item", "projectile", "impact", "child", "field"], help="Sprite validation role.")
    ap.add_argument("--size", type=int, default=48, help="Final canvas size for item tests; use 32 for projectile tests.")
    ap.add_argument("--limit", type=int, default=8, help="How many latest raw cache PNGs to test when paths are omitted.")
    args = ap.parse_args()

    raw_paths = [Path(p) for p in args.paths] if args.paths else latest_raws(args.limit)
    if not raw_paths:
        raise SystemExit("No raw PNGs found. Pass paths or generate sprites first.")

    out_dir = CACHE / "sprite_keyer_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    for raw in raw_paths:
        if not raw.exists():
            print(f"missing: {raw}")
            continue
        sprite_id = f"report_{int(time.time())}_{raw.stem[:48]}"
        final = Path(server.postprocess_sprite(str(raw), sprite_id, int(args.size), args.role))
        validation = server.validate_processed_sprite(str(final), args.role)
        montage = out_dir / f"{sprite_id}_montage.png"
        build_montage(raw, final, montage)
        print(f"RAW     {raw}")
        print(f"FINAL   {final}")
        print(f"MONTAGE {montage}")
        print(f"OK      {validation.get('ok')} reasons={validation.get('reasons')} warnings={validation.get('warnings')}")
        print()


if __name__ == "__main__":
    main()
