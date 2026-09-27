#!/usr/bin/env python3
"""Rasterize captured FNA solid quads, never synthesize VFX shapes.

Usage: <existing-Pillow-python> tools/render_vfx_preview.py capture.json output-dir
CPU polygon coverage is not GPU rasterizer/texture/filter/color-space parity.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw

BG = (13, 18, 28)
ZOOM = 1.5
VIEW = (200, 160)
CELL = (320, 276)


def geometry(frame):
    image = Image.new("RGB", (round(VIEW[0] * ZOOM), round(VIEW[1] * ZOOM)), BG)
    for quad in frame["quads"]:
        colors = quad["colors"]
        if any(c != colors[0] for c in colors):
            raise ValueError("Nonuniform vertex colors require interpolation; refusing misleading preview")
        r, g, b, a = colors[0]
        # FNA quad vertex order is top-left, top-right, bottom-left, bottom-right.
        points = [(quad["positions"][i][0] * ZOOM, quad["positions"][i][1] * ZOOM) for i in (0, 1, 3, 2)]
        x0 = max(0, math.floor(min(p[0] for p in points)))
        y0 = max(0, math.floor(min(p[1] for p in points)))
        x1 = min(image.width, math.ceil(max(p[0] for p in points)) + 1)
        y1 = min(image.height, math.ceil(max(p[1] for p in points)) + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        box = (x0, y0, x1, y1)
        dest = image.crop(box)
        mask = Image.new("L", dest.size)
        ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in points], fill=255)
        # Premultiplied One / InverseSourceAlpha. In particular, A=0 does NOT
        # hide RGB: that is how the actual renderer encodes additive slots.
        faded = dest.point(lambda value: round(value * (255 - a) / 255))
        mixed = ImageChops.add(faded, Image.new("RGB", dest.size, (r, g, b)))
        image.paste(Image.composite(mixed, dest, mask), (x0, y0))
    return image


def cell(frame):
    image = Image.new("RGB", CELL, BG)
    image.paste(geometry(frame), (10, 28))
    draw = ImageDraw.Draw(image)
    draw.text((10, 5), f'{frame["renderer"]} / {frame["blend"]} / tick {frame["tick"]}', fill="white")
    draw.text((10, 258), f'{frame["drawCalls"]}/{frame["budget"]} quads | scale {frame["scale"]} | 1px={ZOOM}px', fill=(140, 160, 185))
    return image


def canvas(columns, rows):
    image = Image.new("RGB", (CELL[0] * columns, CELL[1] * rows + 64), BG)
    draw = ImageDraw.Draw(image)
    draw.text((12, 8), "OFFLINE GEOMETRY / NOT GAME GPU", fill=(255, 205, 90))
    draw.text((12, 26), "REAL FNA CPU QUADS | synthetic input | solid 2x3 texels | explicit effectColor: cyan", fill="white")
    draw.text((12, 43), "No shader, texture sampling, game scene, author backend or visual-quality acceptance claim.", fill=(160, 175, 195))
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raw = args.capture.read_bytes()
    payload = json.loads(raw)
    assert payload["schema"] == "icl.offline-fna-quads.v1"
    frames = payload["captures"]
    kinds = list(dict.fromkeys(f["renderer"] for f in frames))
    ticks = sorted({f["tick"] for f in frames})
    index = {(f["renderer"], f["blend"], f["tick"]): f for f in frames}
    args.output.mkdir(parents=True, exist_ok=True)
    contact = canvas(3, len(kinds))
    for row, kind in enumerate(kinds):
        for col, tick in enumerate([ticks[0], ticks[len(ticks) // 2], ticks[-1]]):
            contact.paste(cell(index[kind, "alpha", tick]), (col * CELL[0], 64 + row * CELL[1]))
    contact.save(args.output / "vfx-preview-contact.png")
    animated = []
    for tick in ticks:
        sheet = canvas(4, math.ceil(len(kinds) * 2 / 4))
        for i, (kind, blend) in enumerate((k, b) for k in kinds for b in ("alpha", "additive")):
            sheet.paste(cell(index[kind, blend, tick]), ((i % 4) * CELL[0], 64 + (i // 4) * CELL[1]))
        animated.append(sheet)
    animated[0].save(args.output / "vfx-preview-first-frame.png")
    animated[0].save(args.output / "vfx-preview.gif", save_all=True, append_images=animated[1:], duration=100, loop=0, disposal=2)
    # Compare shape in projectile-local coordinates; input translation alone
    # must not be mistaken for shape animation. Record aliases, don't hide them.
    signatures = {}
    observations = {}
    for kind in kinds:
        shapes = []
        for tick in ticks:
            frame = index[kind, "alpha", tick]
            cx, cy = (frame["center"][i] - frame["screen"][i] for i in range(2))
            shape = [[[int(round((p[0] - cx) * 100)), int(round((p[1] - cy) * 100))] for p in q["positions"]] for q in frame["quads"]]
            shapes.append(json.dumps(shape, separators=(",", ":")))
        signatures[kind] = shapes
        observations[kind] = {"distinctLocalGeometries": len(set(shapes)), "drawCalls": sorted({index[kind, "alpha", t]["drawCalls"] for t in ticks}),
                              "firstVertexRGBA": index[kind, "alpha", ticks[0]]["quads"][0]["colors"][0]}
    aliases = [[a, b] for i, a in enumerate(kinds) for b in kinds[i + 1:] if signatures[a] == signatures[b]]
    report = {"label": payload["label"], "captureSha256": hashlib.sha256(raw).hexdigest(), "assemblyMvid": payload["assemblyMvid"], "frames": len(frames), "clockFrames": len(ticks), "observations": observations, "identicalGeometryAcrossAllClocks": aliases,
              "proofBoundary": "Geometry and vertex RGB/A from live production Draw; Pillow polygon coverage and GIF quantization are approximations, not game GPU evidence. Re-capture after integration."}
    (args.output / "vfx-preview-observations.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
