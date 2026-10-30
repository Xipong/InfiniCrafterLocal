"""Ordered render layers from certified native draw-call observations.

This is a presentation view, not an execution plan. Unknown APIs/schemas keep the
connected source view. Source bindings, conditions and color mutations survive.
"""
from __future__ import annotations

import copy
from collections import Counter
import json
from dataclasses import replace
from typing import Any

from infini_local.pipelines.native_attack_expression_view import _Parser, _Term, _render

_SPRITE = "XnaGfx.SpriteBatch.Draw(XnaGfx.Texture2D,Xna.Vector2,System.Nullable`1[[Xna.Rectangle, FNA]],Xna.Color,float,Xna.Vector2,float,XnaGfx.SpriteEffects,float)"
_SPARKLE = "T.Main.DrawPrettyStarSparkle(float,XnaGfx.SpriteEffects,Xna.Vector2,Xna.Color,Xna.Color,float,float,float,float,float,float,Xna.Vector2,Xna.Vector2)"
_FRAME = "T.Utils.Frame(Content.Asset`1[[XnaGfx.Texture2D, FNA]],int,int,int,int,int,int)"
_ASSET = "Content.Asset`1[[XnaGfx.Texture2D, FNA]].get_Value()"
_NULLABLE = "System.Nullable`1[[Xna.Rectangle, FNA]]..ctor(Xna.Rectangle)"
_REMAP = "T.Utils.Remap(float,float,float,float,float,bool)"
_SPRITE_ARGS = ("texture", "position", "sourceRectangle", "color", "rotation", "origin", "scale", "effects", "layerDepth")
_SPARKLE_ARGS = ("opacity", "dir", "drawpos", "drawColor", "shineColor", "flareCounter", "fadeInStart", "fadeInEnd", "fadeOutStart", "fadeOutEnd", "rotation", "scale", "fatness")
_FRAME_ARGS = ("tex", "horizontalFrames", "verticalFrames", "frameX", "frameY", "sizeOffsetX", "sizeOffsetY")
# Narrow native presentation primitives, not a renderer/item allowlist. A new
# opaque operation keeps the complete symbolic view until its API is understood.
_KNOWN_SIGNATURES = {
    'Content.Asset`1[[XnaGfx.Texture2D, FNA]].get_Value()',
    'System.Math.Sqrt(double)',
    'System.Nullable`1[[Xna.Rectangle, FNA]]..ctor(Xna.Rectangle)',
    'T.Entity.get_Center()',
    'T.GameContent.TextureAssets.Projectile',
    'T.Lighting.GetColor(Xna.Point)',
    'T.Main.DrawPrettyStarSparkle(float,XnaGfx.SpriteEffects,Xna.Vector2,Xna.Color,Xna.Color,float,float,float,float,float,float,Xna.Vector2,Xna.Vector2)',
    'T.Projectile.get_Opacity()',
    'T.Utils.Frame(Content.Asset`1[[XnaGfx.Texture2D, FNA]],int,int,int,int,int,int)',
    'T.Utils.Remap(float,float,float,float,float,bool)',
    'T.Utils.Size(Xna.Rectangle)',
    'T.Utils.ToRotationVector2(float)',
    'T.Utils.ToTileCoordinates(Xna.Vector2)',
    'T.Utils.Width(Content.Asset`1[[XnaGfx.Texture2D, FNA]])',
    'Xna.Color..ctor(int,int,int)',
    'Xna.Color..ctor(int,int,int,int)',
    'Xna.Color.ToVector3()',
    'Xna.Color.get_A()',
    'Xna.Color.get_G()',
    'Xna.Color.get_R()',
    'Xna.Color.get_White()',
    'Xna.Color.op_Multiply(Xna.Color,float)',
    'Xna.Color.set_A(byte)',
    'Xna.Color.set_B(byte)',
    'Xna.Color.set_G(byte)',
    'Xna.Vector2..ctor(float,float)',
    'Xna.Vector2.get_One()',
    'Xna.Vector2.op_Addition(Xna.Vector2,Xna.Vector2)',
    'Xna.Vector2.op_Division(Xna.Vector2,float)',
    'Xna.Vector2.op_Multiply(Xna.Vector2,float)',
    'Xna.Vector2.op_Subtraction(Xna.Vector2,Xna.Vector2)',
    'Xna.Vector3.Length()',
    'XnaGfx.SpriteBatch.Draw(XnaGfx.Texture2D,Xna.Vector2,System.Nullable`1[[Xna.Rectangle, FNA]],Xna.Color,float,Xna.Vector2,float,XnaGfx.SpriteEffects,float)',
}

_SOURCE_OPERATIONS = {"add", "sub", "mul", "div", "ldfld", "ldsfld", "stfld", "ldelem.r4", "ldelem.ref", "ldelem.i4",
                      "conv.r4", "conv.r8", "conv.u1", "conv.i4", "alternatives", "source_block", "requires", "value",
                      "unresolved", "loop_or_alias", "address_or_written"}
_SCOPE = (
    "Layers execute in source step order, subject to blocks/conditions; loops are not unrolled. "
    "Sprite defaults are literal shared expressions read at each layer, not cached values. "
    "Definitions bind at their original step; addressed color writes keep their order. "
    "frame uses native integer texture-grid slicing and size offsets; rgb has alpha 255. "
    "Utils.Remap(value,inMin,inMax,outMin,outMax,clamp) maps the input range linearly; clamp=1 bounds its normalized input. "
    "fade scales all RGBA channels, not alpha alone. Duplicate Color construction observations "
    "and qualified signatures are omitted; their expressions/writes remain. GPU extent and external hooks remain unresolved."
)


def _terms(term: _Term):
    yield term
    for child in term.args or ():
        yield from _terms(child)


def _expressions(program: dict) -> list[str]:
    result = []
    for row in [*program["observations"], *program["dependencies"].values()]:
        for item in [row, *row.get("orderedSourceUses", [])]:
            result.extend(item[key] for key in ("expression", "receiver") if key in item)
            result.extend(item.get("arguments", {}).values())
    for predicate in program["predicates"]:
        result.extend(predicate.get("inputs", []))
    if not all(isinstance(value, str) for value in result):
        raise ValueError("non-expression cell")
    return result


def _tree(text: str) -> _Term:
    term = _Parser(text, compact=True).parse()
    if _render(term, compact=True) != text:
        raise ValueError("unsupported expression spelling")
    return term


def _role_names(program: dict, trees: list[_Term]) -> dict[str, str]:
    dependencies = program["dependencies"]
    symbols = program["symbols"]
    names: dict[str, str] = {}
    identifiers = {term.name for tree in trees for term in _terms(tree)}

    def name(old: str, proposed: str) -> None:
        if old in dependencies and old not in names and proposed not in identifiers and proposed not in names.values():
            names[old] = proposed

    sprites = [row for row in program["observations"] if row["call"] == "SpriteBatch.Draw"]
    for key, label in (("position", "position"), ("origin", "origin"), ("scale", "spriteScale"), ("effects", "effects")):
        values = {row["arguments"][key] for row in sprites if row["arguments"][key] in dependencies}
        if len(values) == 1:
            name(next(iter(values)), label)
    for key, operation, label in (("texture", "Asset`1.get_Value", "textureAsset"), ("sourceRectangle", "Nullable`1..ctor", "frameRect")):
        values = {_tree(row["arguments"][key]).args[0].name for row in sprites
                  if _tree(row["arguments"][key]).name == operation and len(_tree(row["arguments"][key]).args or ()) == 1
                  and _tree(row["arguments"][key]).args[0].args is None}
        if len(values) == 1:
            name(next(iter(values)), label)
    tint = 0
    for row in program["observations"]:
        if symbols.get(row["call"]) == "Xna.Color..ctor(int,int,int)" and row.get("receiver") in dependencies:
            tint += 1
            name(row["receiver"], f"tint{tint}")
    # A native remap-up times remap-down, applied to a tint, is an envelope;
    # neither the phase's meaning nor its numeric values are guessed/evaluated.
    if symbols.get("Utils.Remap") == _REMAP:
        color_atoms = {term.name for row in sprites for term in _terms(_tree(row["arguments"]["color"]))}
        candidates = []
        for key, row in dependencies.items():
            tree = _tree(row["expression"]) if "expression" in row else None
            if tree is None or tree.name != "mul" or len(tree.args or ()) != 2 or key not in color_atoms:
                continue
            left, right = tree.args
            if (left.name == right.name == "Utils.Remap" and len(left.args or ()) == len(right.args or ()) == 6
                    and left.args[0] == right.args[0]
                    and [arg.name for arg in left.args[3:]] == ["0", "1", "1"]
                    and [arg.name for arg in right.args[3:]] == ["1", "0", "1"]):
                candidates.append((key, left.args[0]))
        if len(candidates) == 1:
            key, phase = candidates[0]
            name(key, "fade")
            if phase.args is None:
                name(phase.name, "fadeInput")
    return names


def _display(tree: _Term, names: dict[str, str], symbols: dict) -> str:
    def visit(term: _Term) -> _Term:
        if term.args is None:
            return replace(term, name=names.get(term.name, term.name))
        args = tuple(visit(child) for child in term.args)
        signature = symbols.get(term.name)
        if signature in (_ASSET, _NULLABLE) and len(args) == 1:
            return args[0]
        if signature == _FRAME and len(args) == 7:
            labelled = (args[0], *( _Term(label, (child,), "=") for label, child in zip(
                ("columns", "rows", "x", "y", "offsetX", "offsetY"), args[1:])))
            return _Term("frame", labelled, "(", (",",) * 6)
        if signature in ("Xna.Color..ctor(int,int,int)", "Xna.Color..ctor(int,int,int,int)"):
            count = 3 if signature == "Xna.Color..ctor(int,int,int)" else 4
            if len(args) in (count, count + 1):
                label = ("rgb" if count == 3 else "rgba") if len(args) == count else ("writeRGB" if count == 3 else "writeRGBA")
                return _Term(label, args, "(", (",",) * (len(args) - 1))
        return replace(term, args=args)
    return _render(visit(tree), compact=True)


def project_draw_layers(source: dict, program: dict, certificates: list) -> dict | None:
    """Recognize API primitives, never renderer names, families or item IDs."""
    cert_keys = ("method", "sourceModuleVersionId", "sourceMethodSha256")
    if (not isinstance(certificates, list) or not all(type(source.get(key)) is str for key in cert_keys)
            or not any(isinstance(cert, dict) and all(cert.get(key) == source[key] for key in cert_keys) for cert in certificates)
            or not set(program) <= {"method", "observations", "dependencies", "predicates", "symbols", "unresolved", "identitySelection"}
            or not all(isinstance(program.get(key), kind) for key, kind in (("observations", list), ("dependencies", dict), ("predicates", list), ("symbols", dict)))):
        return None
    symbols = program["symbols"]
    if any(not isinstance(signature, str) or signature not in _KNOWN_SIGNATURES for signature in symbols.values()):
        return None
    sprite_rows, factories = [], []
    for row in program["observations"]:
        if (not isinstance(row, dict) or not set(row) <= {"kind", "step", "block", "requiredPredicates", "call", "receiver", "arguments"}
                or row.get("kind") != "draw_call" or not isinstance(row.get("call"), str)
                or not isinstance(row.get("arguments"), dict)):
            return None
        signature = symbols.get(row.get("call"))
        if signature == _SPRITE and row["call"] == "SpriteBatch.Draw":
            expected = _SPRITE_ARGS
            sprite_rows.append(row)
        elif signature == _SPARKLE and row["call"] == "Main.DrawPrettyStarSparkle":
            expected = _SPARKLE_ARGS
        elif signature == _FRAME:
            expected = _FRAME_ARGS
            factories.append(row)
        elif signature == "Xna.Color..ctor(int,int,int)":
            expected = ("r", "g", "b")
            factories.append(row)
        elif signature == "Xna.Color..ctor(int,int,int,int)":
            expected = ("r", "g", "b", "alpha")
            factories.append(row)
        else:
            return None
        if tuple(row["arguments"]) != expected:
            return None
    if not sprite_rows:
        return None
    try:
        trees = [_tree(text) for text in _expressions(program)]
        if any(term.args is not None and term.name not in symbols and term.name not in _SOURCE_OPERATIONS
               for tree in trees for term in _terms(tree)):
            return None
        # A constructor observation duplicates an addressed write only when
        # expression, source step, block and conditions all agree. Other setup
        # calls retain their original evaluation point in a separate section.
        def record(expression: str, row: dict) -> tuple:
            return expression, row.get("step"), row.get("block"), json.dumps(row.get("requiredPredicates"), separators=(",", ":"))

        uses = Counter(record(use.get("expression"), use) for dependency in program["dependencies"].values()
                       for use in dependency.get("orderedSourceUses", []))
        duplicate_factory_indices = set()
        for index, row in enumerate(program["observations"]):
            if row not in factories:
                continue
            args = ([row["receiver"]] if "receiver" in row else []) + list(row["arguments"].values())
            key = record(row["call"] + "[" + ",".join(args) + "]", row)
            if uses[key] > 0:
                uses[key] -= 1
                duplicate_factory_indices.add(index)
        names = _role_names(program, trees)
        display = lambda text: _display(_tree(text), names, symbols)
        definitions = copy.deepcopy(program["dependencies"])
        for row in definitions.values():
            for use in [row, *row.get("orderedSourceUses", [])]:
                if "expression" in use:
                    use["expression"] = display(use["expression"])
        definitions = {names.get(key, key): row for key, row in definitions.items()}
        layers = []
        setup = []
        for index, row in enumerate(program["observations"]):
            if index in duplicate_factory_indices:
                continue
            if row in factories:
                args = ([row["receiver"]] if "receiver" in row else []) + list(row["arguments"].values())
                setup.append({**{key: copy.deepcopy(row[key]) for key in ("step", "block", "requiredPredicates") if key in row},
                              "expression": display(row["call"] + "[" + ",".join(args) + "]")})
                continue
            sprite = row["call"] == "SpriteBatch.Draw"
            args = {key: display(value) for key, value in row["arguments"].items()}
            if sprite:
                args["frame"] = args.pop("sourceRectangle")
                args["tint"] = args.pop("color")
            layers.append({"kind": "sprite" if sprite else "nativeStarSparkle",
                           **{key: copy.deepcopy(row[key]) for key in ("step", "block", "requiredPredicates") if key in row},
                           **({"renderer": display(row["receiver"])} if "receiver" in row else {}), **args})
        conditions = copy.deepcopy(program["predicates"])
        for row in conditions:
            row["inputs"] = [display(value) for value in row["inputs"]]
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
        return None
    sprites = [layer for layer in layers if layer["kind"] == "sprite"]
    shared = {}
    if len(sprites) >= 2:
        for key in ("texture", "position", "origin", "effects", "layerDepth", "renderer"):
            if key in sprites[0] and all(layer.get(key) == sprites[0][key] for layer in sprites):
                shared[key] = sprites[0][key]
                for layer in sprites:
                    del layer[key]
    return {"method": program["method"], "renderLayerView": {"version": 1, "scope": _SCOPE},
            **({"spriteLayerDefaults": shared} if shared else {}), "layers": layers,
            "definitions": definitions, "conditions": conditions, **({"setup": setup} if setup else {}),
            **{key: copy.deepcopy(program[key]) for key in ("unresolved", "identitySelection") if key in program}}
