"""Bounded authored contour DAG and independent textured draw operations.

Geometry is presentation only. Resolution implements literal affine/closure math;
no shape recognition, inferred bridge, gameplay geometry or generated code.
"""

from __future__ import annotations

import math
import struct
from typing import Any

from infini_local.core.vfx.materials import _number, _object, _profile, rgb_schema, texture_schema

MAX_CONTOUR_POINTS = 128
MAX_TOTAL_POINTS = 512
# Legacy wire calls these draw calls; each unit bounds one quad-equivalent
# (two triangles), not one actual GPU submission. Compiler-owned, not a prompt knob.
MAX_DRAW_WORK_UNITS = 2048
CONTOUR_SEMANTICS = (
    "Named static contours compose line/ellipseArc/polyline/transform/close/concat/trim in a bounded acyclic graph. "
    "concat sources require coincident endpoints, never an inferred bridge. trim preserves interior corners over normalized arclength start/end; decreasing range explicitly reverses, equal endpoints give a point, no wrap. Forward references are allowed; ids are local to this slot. Coordinates are world pixels in the selected frame. "
    "ellipseArc starts at startRadians and follows signed sweepRadians; a full turn is closed. "
    "close appends its explicit via points then the first point; empty via makes a straight closing chord. "
    "transform applies component scale, then rotation, then translation. No inferred connecting curves. "
    "Independent draws select stroke, simple closed fill, or band between two equally open/closed contours. "
    "Band pairs normalized arclength, preserves both boundaries' corners and uses authored start/direction; no auto reverse. "
    "Each draw owns an exact existing material texture/UV/sampling and lifetime RGB/opacity; solidPixel makes an untextured-looking surface. Stroke/band multiply opacityProfile along length by lifetime opacity; no extra glow/fade. Fill mapping is local planar UV=(point-origin)/size before scene transform. Stroke/band mapping follows contour length and across-width V; band repeat uses first boundary length. Texture UV transforms apply last. "
    "Stroke width is world pixels after the common scene transform; joins/caps/miterLimit are explicit. Genuine self-crossing stroke segments composite literally, so overlap repeats alpha/additive coverage; no polygon union or guessed round cusp. Fill addressMode explicitly chooses clamp or repeat. "
    "Scene transformStart/End interpolate linearly over duration, then source/world frame is applied. "
    "world attachment captures event pose; source follows that exact generation and retires with it. "
    "All draw topology is static; the common affine animation does not invent intermediate contour shapes. "
    "Filled/band meshes consume shared draw budget atomically, never a partial silhouette. "
    "Textures reuse exact item/entity or declared asset PNGs, or curated library resources. Only declared assets request generation. No particles, lighting, collision or gameplay is added. Consecutive points within 1e-6 pixels are one native float32 point; band sample fractions within 1e-6 of a corner use that exact corner; curve tessellation is technical lowering."
)


def _point_schema():
    return {"type": "array", "minItems": 2, "maxItems": 2, "items": _number(-512, 512, "World pixels.")}


def _contour_id_schema():
    return {"type": "string", "minLength": 1, "maxLength": 48, "pattern": r"^[a-z][a-z0-9_]*$", "not": {"pattern": r"[^a-z0-9_]"}}


def affine_schema():
    return _object(
        {
            "translate": _point_schema(),
            "scale": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": _number(-4, 4, "Independent dimensionless axis scale; zero is silent."),
            },
            "rotationRadians": _number(-math.tau, math.tau, "Rotation after scale, before translation."),
        }
    )


def _tagged_object_schema(common, variants):
    fields = {key: val for row in variants.values() for key, val in row.items()}
    schema = {"type": "object", "additionalProperties": False, "properties": {**common, **fields}, "required": list(common)}
    selector = "kind" if "kind" in common else "op"
    schema["allOf"] = [
        {
            "if": {"properties": {selector: {"const": kind}}, "required": [selector]},
            "then": {
                "required": list(row),
                "properties": {
                    **{key: value for key, value in row.items() if key == "mapping" or value != fields[key]},
                    **{key: {"enum": []} for key in fields if key not in row},
                },
            },
        }
        for kind, row in variants.items()
    ]
    return schema


def contour_schema():
    variants = {
        "line": {"from": _point_schema(), "to": _point_schema()},
        "ellipseArc": {
            "center": _point_schema(),
            "radiusX": _number(0, 256, "World-pixel radius."),
            "radiusY": _number(0, 256, "World-pixel radius."),
            "startRadians": _number(-math.tau, math.tau, "Authored seam angle."),
            "sweepRadians": _number(-math.tau, math.tau, "Signed sweep; full turn closes."),
            "segments": _number(3, 64, "Tessellation segments.", integer=True),
        },
        "concat": {"sources": {"type": "array", "minItems": 2, "maxItems": 16, "items": _contour_id_schema()}},
        "trim": {
            "source": _contour_id_schema(),
            "start": _number(0, 1, "Normalized arclength start; greater than end reverses explicitly."),
            "end": _number(0, 1, "Normalized arclength end; equal start is one point, no wrap."),
        },
        "polyline": {"points": {"type": "array", "minItems": 2, "maxItems": 64, "items": _point_schema()}},
        "transform": {"source": _contour_id_schema(), **affine_schema()["properties"]},
        "close": {"source": _contour_id_schema(), "via": {"type": "array", "maxItems": 8, "items": _point_schema()}},
    }
    node = _tagged_object_schema({"id": _contour_id_schema(), "kind": {"type": "string", "enum": list(variants)}}, variants)
    texture = texture_schema()
    texture["required"].append("uv")
    texture["properties"]["source"]["enum"] = ["item", "entity", "asset", "library"]
    material = _object(
        {
            "texture": texture,
            "sampling": {"type": "string", "enum": ["point", "linear"]},
            "colorStart": rgb_schema(),
            "colorEnd": rgb_schema(),
            "opacityStart": _number(0, 1, "Initial opacity."),
            "opacityEnd": _number(0, 1, "Final opacity; no additional fade."),
        }
    )
    operations = {
        "stroke": {
            "contour": _contour_id_schema(),
            "widthPx": _number(0, 128, "World-pixel width after common scene transform."),
            "join": {"type": "string", "enum": ["bevel", "miter"]},
            "cap": {"type": "string", "enum": ["butt", "square"]},
            "miterLimit": _number(1, 8, "Miter length divided by half width; exceeding joins bevel."),
        },
        "fill": {"contour": _contour_id_schema()},
        "band": {"first": _contour_id_schema(), "second": _contour_id_schema()},
    }
    planar = _object(
        {
            "origin": _point_schema(),
            "addressMode": {"type": "string", "enum": ["clamp", "repeat"]},
            "size": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": _number(0.001, 4096, "Local-plane pixels per full texture repeat."),
            },
        }
    )
    path_mapping = _object(
        {
            "mode": {"type": "string", "enum": ["stretch", "repeat"]},
            "repeatLengthPx": _number(1, 512, "Pixels per texture repeat along contour."),
            "scrollPxPerTick": _number(-32, 32, "World-tick UV scroll; stretch requires zero."),
        }
    )
    path_mapping["allOf"] = [
        {
            "if": {"properties": {"mode": {"const": "stretch"}}, "required": ["mode"]},
            "then": {"properties": {"repeatLengthPx": {"const": 1}, "scrollPxPerTick": {"const": 0}}},
        }
    ]
    for op, row in operations.items():
        row["mapping"] = planar if op == "fill" else path_mapping
        if op != "fill":
            row["opacityProfile"] = _profile(1)
    draw = _tagged_object_schema({"op": {"type": "string", "enum": list(operations)}, "material": material}, operations)
    draw["properties"]["mapping"] = {"anyOf": [planar, path_mapping]}
    return _object(
        {
            "attachment": {"type": "string", "enum": ["world", "source"]},
            "rotationFrame": {"type": "string", "enum": ["world", "source"]},
            "transformStart": affine_schema(),
            "transformEnd": affine_schema(),
            "contours": {"type": "array", "minItems": 1, "maxItems": 16, "items": node},
            "draws": {"type": "array", "minItems": 1, "maxItems": 16, "items": draw},
        }
    )


def contour_slot_clauses(item_ids, renderers, events):
    selected = {"rendererKind": {"const": "contour"}}

    def when(values, then):
        return {"if": {"properties": values, "required": list(values)}, "then": then}

    return [
        when(selected, {"required": ["geometry"], "properties": {"phaseOffset": {"enum": []}}}),
        when({"rendererKind": {"enum": [r for r in renderers if r != "contour"]}}, {"properties": {"geometry": {"enum": []}}}),
        when({**selected, "event": {"const": "periodic"}}, {"properties": {"repeatEvery": {"minimum": 1}}}),
        when({**selected, "event": {"enum": [e for e in events if e != "periodic"]}}, {"properties": {"repeatEvery": {"const": 0}}}),
        when({**selected, "event": {"const": "periodic"}, "entityId": {"enum": item_ids}}, {"properties": {"startTick": {"const": 0}}}),
        when(
            {**selected, "event": {"enum": ["on_expire", "on_kill"]}},
            {"properties": {"geometry": {"properties": {"attachment": {"const": "world"}}}}},
        ),
    ]


def contour_texture_clauses(rows):
    """Advertise only this entity's real PNG producers in the one-shot schema."""
    clauses = []
    for row in rows:
        texture = {"properties": {"source": {"enum": [source for source in row["sources"] if source != "impact"]}}}
        material = {"properties": {"texture": texture}}
        draw = {"properties": {"material": material}}
        geometry = {"properties": {"draws": {"items": draw}}}
        clauses.append(
            {
                "if": {
                    "properties": {"rendererKind": {"const": "contour"}, "entityId": {"const": row["entityId"]}},
                    "required": ["rendererKind", "entityId"],
                },
                "then": {"properties": {"geometry": geometry}},
            }
        )
    return clauses


_EPS = 1e-7
_SAME_EPS = 1e-6


def _float32(v):
    # Native DTOs and Vector2 arithmetic use float32. Match rounding at each
    # operation rather than admitting a double-only contour the engine rejects.
    return struct.unpack("f", struct.pack("f", v))[0]


def _point32(p):
    return (_float32(p[0]), _float32(p[1]))


def _same_point(a, b):
    return abs(a[0] - b[0]) <= _SAME_EPS and abs(a[1] - b[1]) <= _SAME_EPS


def _cross_product(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _intersects(a, b, c, d):
    x, y, z, w = _cross_product(a, b, c), _cross_product(a, b, d), _cross_product(c, d, a), _cross_product(c, d, b)

    def on(p, q, r):
        return min(p[0], q[0]) - _EPS <= r[0] <= max(p[0], q[0]) + _EPS and min(p[1], q[1]) - _EPS <= r[1] <= max(p[1], q[1]) + _EPS

    return ((x > _EPS and y < -_EPS or x < -_EPS and y > _EPS) and (z > _EPS and w < -_EPS or z < -_EPS and w > _EPS)) or any(
        abs(k) <= _EPS and on(p, q, r) for k, p, q, r in ((x, a, b, c), (y, a, b, d), (z, c, d, a), (w, c, d, b))
    )


def _is_simple(points, closed):
    edges = list(zip(points, points[1:]))
    for i, (a, b) in enumerate(edges):
        if _same_point(a, b):
            continue
        for j, (c, d) in enumerate(edges[i + 1 :], i + 1):
            if j == i + 1 or closed and i == 0 and j == len(edges) - 1:
                continue
            if _same_point(c, d):
                continue
            if _intersects(a, b, c, d):
                return False
    return True


def _contour_fractions(points):
    if len(points) < 2:
        raise ValueError("band contours need nonzero length")
    values = [0.0]
    for a, b in zip(points, points[1:]):
        delta = _subtract(b, a)
        distance = _float32(math.sqrt(_dot(delta, delta)))
        values.append(_float32(values[-1] + distance))
    if values[-1] <= 0:
        raise ValueError("band contours need nonzero length")
    return [_float32(v / values[-1]) for v in values]


def _sample_contour(points, values, t):
    if t in values:
        return points[values.index(t)]
    for i in range(1, len(values)):
        if values[i] > t:
            # Preserve the exact authored corner when the parameter differs
            # only by native float32 arclength accumulation noise.
            if abs(values[i] - t) <= 1e-6:
                return points[i]
            if abs(values[i - 1] - t) <= 1e-6:
                return points[i - 1]
            fraction = _float32(_float32(t - values[i - 1]) / _float32(values[i] - values[i - 1]))
            return _add(points[i - 1], _multiply(_subtract(points[i], points[i - 1]), fraction))
    return points[-1]


def _trim_contour(points, start, end):
    if len(points) <= 1:
        return list(points)
    start, end = _float32(start), _float32(end)
    fractions = _contour_fractions(points)
    lo, hi = min(start, end), max(start, end)
    kept = [_sample_contour(points, fractions, lo)]
    kept.extend(point for point, fraction in zip(points, fractions) if lo < fraction < hi)
    kept.append(_sample_contour(points, fractions, hi))
    return list(reversed(kept)) if start > end else kept


def _band_triangles(first, second):
    fa, fb = _contour_fractions(first), _contour_fractions(second)
    knots = sorted(set(fa + fb + [0.5]))
    triangles = []
    sign = None
    for lo, hi in zip(knots, knots[1:]):
        quad = [
            _sample_contour(first, fa, lo),
            _sample_contour(first, fa, hi),
            _sample_contour(second, fb, hi),
            _sample_contour(second, fb, lo),
        ]
        # Keep every arclength knot and boundary corner. Float32-equivalent
        # consecutive endpoints collapse a thin quad to a triangle or silence,
        # never to a repaired/reversed contour.
        cell = [point for index, point in enumerate(quad) if index == 0 or not _same_point(point, quad[index - 1])]
        if len(cell) > 1 and not _same_point(cell[0], cell[-1]):
            cell.append(cell[0])
        cell_triangles = _triangulate_fill(cell)
        if not cell_triangles:
            continue
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(quad, quad[1:] + quad[:1])) * 0.5
        if abs(area) <= _EPS:
            raise ValueError("band has numerically ambiguous correspondence")
        if sign is not None and sign != (area > 0):
            raise ValueError("band correspondence reverses orientation")
        sign = area > 0
        triangles.extend(cell_triangles)
    _reject_overlapping_mesh(triangles, "band triangles overlap")
    return triangles


def _add(a, b):
    return (_float32(a[0] + b[0]), _float32(a[1] + b[1]))


def _subtract(a, b):
    return (_float32(a[0] - b[0]), _float32(a[1] - b[1]))


def _multiply(a, scalar):
    return (_float32(a[0] * scalar), _float32(a[1] * scalar))


def _dot(a, b):
    return _float32(_float32(a[0] * b[0]) + _float32(a[1] * b[1]))


def _inside(point, a, b, c, *, strict=False):
    values = (_cross_product(a, b, point), _cross_product(b, c, point), _cross_product(c, a, point))
    return all(value > _EPS for value in values) if strict else all(value >= -_EPS for value in values)


def _triangulate_fill(points):
    """Same bounded simple-polygon ear clipping as the native mesh owner."""
    if len(points) <= 1:
        return []
    closed = len(points) > 2 and _same_point(points[0], points[-1])
    if closed and all(abs(_cross_product(points[0], points[1], p)) <= _EPS for p in points[2:]):
        return []
    if not closed or len(points) < 4:
        raise ValueError("fill requires a closed contour with at least three vertices")
    if not _is_simple(points, True):
        raise ValueError("fill contour intersects or touches itself")
    polygon = list(points[:-1])
    changed = True
    while changed and len(polygon) > 3:
        changed = False
        for i, point in enumerate(polygon):
            before, after = polygon[i - 1], polygon[(i + 1) % len(polygon)]
            if abs(_cross_product(before, after, point)) <= _EPS and all(
                min(before[k], after[k]) - _EPS <= point[k] <= max(before[k], after[k]) + _EPS for k in (0, 1)
            ):
                polygon.pop(i)
                changed = True
                break
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1])) / 2
    if abs(area) <= _EPS:
        raise ValueError("fill contour has zero or numerically ambiguous area")
    if area < 0:
        polygon.reverse()
    triangles = []
    while len(polygon) > 3:
        for i, b in enumerate(polygon):
            prev, nxt = (i - 1) % len(polygon), (i + 1) % len(polygon)
            a, c = polygon[prev], polygon[nxt]
            if _cross_product(a, b, c) <= _EPS:
                continue
            if any(_inside(p, a, b, c) for j, p in enumerate(polygon) if j not in (prev, i, nxt)):
                continue
            triangles.append((a, b, c))
            polygon.pop(i)
            break
        else:
            raise ValueError("fill triangulation is numerically ambiguous")
    triangles.append(tuple(polygon))
    return triangles


def _triangles_overlap(first, second):
    # Reject disjoint bounds before the exact finite edge/containment tests.
    for axis in (0, 1):
        if (
            max(p[axis] for p in first) < min(p[axis] for p in second) - _EPS
            or max(p[axis] for p in second) < min(p[axis] for p in first) - _EPS
        ):
            return False

    def centroid(triangle):
        total = _add(_add(triangle[0], triangle[1]), triangle[2])
        return (_float32(total[0] / 3), _float32(total[1] / 3))

    if _inside(centroid(first), *second, strict=True) or _inside(centroid(second), *first, strict=True):
        return True
    if any(_inside(p, *second, strict=True) for p in first) or any(_inside(p, *first, strict=True) for p in second):
        return True
    for i in range(3):
        a, b = first[i], first[(i + 1) % 3]
        for j in range(3):
            c, d = second[j], second[(j + 1) % 3]
            if any(_same_point(p, q) for p in (a, b) for q in (c, d)):
                continue
            x, y = _cross_product(a, b, c), _cross_product(a, b, d)
            z, w = _cross_product(c, d, a), _cross_product(c, d, b)
            if ((x > _EPS and y < -_EPS) or (x < -_EPS and y > _EPS)) and ((z > _EPS and w < -_EPS) or (z < -_EPS and w > _EPS)):
                return True
    return False


def _reject_overlapping_mesh(triangles, message):
    for i, first in enumerate(triangles):
        for second in triangles[i + 1 :]:
            if _triangles_overlap(first, second):
                raise ValueError(message)


def _transform_points(points, node):
    sx, sy = _point32(node["scale"])
    tx, ty = _point32(node["translate"])
    c, s = _float32(math.cos(_float32(node["rotationRadians"]))), _float32(math.sin(_float32(node["rotationRadians"])))
    result = []
    for x, y in points:
        x, y = _float32(x * sx), _float32(y * sy)
        result.append(
            (_float32(tx + _float32(_float32(c * x) - _float32(s * y))), _float32(ty + _float32(_float32(s * x) + _float32(c * y))))
        )
    return result


def resolve_contours(geometry: dict[str, Any], path="$.geometry"):
    """Resolve schema-valid static graph for admission and executable tests."""
    errors = []
    nodes = {}
    positions = {}
    result = {}
    visiting = set()

    def error(suffix, message):
        errors.append({"path": path + suffix, "message": message})

    for i, node in enumerate(geometry["contours"]):
        key = node["id"]
        if key in nodes:
            error(f".contours[{i}].id", "duplicate contour id")
        else:
            nodes[key] = node
            positions[key] = i

    def visit(key):
        if key in result:
            return result[key]
        if key in visiting:
            return None
        node = nodes[key]
        base = f".contours[{positions[key]}]"
        visiting.add(key)
        kind = node["kind"]
        points = []
        if kind in {"transform", "close", "trim"}:
            source = node["source"]
            if source not in nodes:
                error(base + ".source", "missing contour reference")
            elif source in visiting:
                error(base + ".source", "cyclic contour reference")
            else:
                parent = visit(source)
                if parent is not None:
                    if kind == "transform":
                        points = _transform_points(parent, node)
                    elif kind == "trim":
                        points = _trim_contour(parent, node["start"], node["end"])
                    else:
                        points = list(parent) + [_point32(p) for p in node["via"]]
                    if kind == "close" and points and not _same_point(points[-1], points[0]):
                        points.append(points[0])
        elif kind == "concat":
            for index, source in enumerate(node["sources"]):
                source_path = base + f".sources[{index}]"
                if source not in nodes:
                    error(source_path, "missing contour reference")
                    break
                if source in visiting:
                    error(source_path, "cyclic contour reference")
                    break
                part = visit(source)
                if not part:
                    break
                if points and not _same_point(points[-1], part[0]):
                    error(source_path, "concat endpoints must coincide; author an explicit line for a bridge")
                    break
                points.extend(part[1:] if points else part)
                if len(points) > MAX_CONTOUR_POINTS:
                    break
        elif kind == "line":
            points = [_point32(node["from"]), _point32(node["to"])]
        elif kind == "polyline":
            points = [_point32(p) for p in node["points"]]
        elif kind == "ellipseArc":
            cx, cy = _point32(node["center"])
            n = node["segments"]
            for i in range(n + 1):
                angle = _float32(_float32(node["startRadians"]) + _float32(_float32(_float32(node["sweepRadians"]) * i) / n))
                points.append(
                    (
                        _float32(cx + _float32(_float32(math.cos(angle)) * _float32(node["radiusX"]))),
                        _float32(cy + _float32(_float32(math.sin(angle)) * _float32(node["radiusY"]))),
                    )
                )
            if abs(abs(_float32(node["sweepRadians"])) - _float32(math.tau)) < 1e-6:
                points[-1] = points[0]
        points = [point for i, point in enumerate(points) if i == 0 or not _same_point(point, points[i - 1])]
        visiting.remove(key)
        if len(points) > MAX_CONTOUR_POINTS:
            error(base, "expanded contour exceeds 128 points")
            return None
        if any(not math.isfinite(x) or not math.isfinite(y) or abs(x) > 8192 or abs(y) > 8192 for x, y in points):
            error(base, "expanded coordinates exceed finite world-pixel envelope")
            return None
        result[key] = points
        return points

    for key in nodes:
        visit(key)
    total_points = 0
    for key, points in result.items():
        total_points += len(points)
        if total_points > MAX_TOTAL_POINTS:
            error(f".contours[{positions[key]}]", "this contour exceeds remaining expanded graph point budget (512 total)")
            break
    for i, draw in enumerate(geometry["draws"]):
        base = f".draws[{i}]"
        refs = ("first", "second") if draw["op"] == "band" else ("contour",)
        for field in refs:
            if draw[field] not in nodes:
                error(base + "." + field, "missing contour reference")
        if any(not result.get(draw[f]) for f in refs):
            continue
        if draw["op"] == "fill":
            try:
                _triangulate_fill(result[draw["contour"]])
            except ValueError as exc:
                error(base + ".contour", str(exc))
        elif draw["op"] == "band":
            first, second = (result[draw[f]] for f in refs)
            closed = _same_point(first[0], first[-1])
            other = _same_point(second[0], second[-1])
            if closed != other:
                error(base + ".second", "band boundaries must both be open or both closed")
            elif not _is_simple(first, closed) or not _is_simple(second, closed):
                error(base + ".second", "band boundaries must be simple")
            elif any(_intersects(a, b, c, d) for a, b in zip(first, first[1:]) for c, d in zip(second, second[1:])):
                error(base + ".second", "band boundaries intersect")
            else:
                try:
                    _band_triangles(first, second)
                except ValueError as exc:
                    error(base + ".second", str(exc))
    return result, errors


def contour_slot_errors(slot, path):
    from infini_local.core.schema_validation import strict_schema_errors

    if slot.get("rendererKind") != "contour":
        return []
    geometry = slot.get("geometry")
    if strict_schema_errors(geometry, contour_schema()):
        return []
    return resolve_contours(geometry, path + ".geometry")[1]


def contour_draw_costs(geometry):
    """Conservative native half-triangle costs for one complete emitted scene.

    Stroke joins can change under affine animation; retain their worst-case
    count. Path midpoint insertion is included, independent of opacity values.
    """
    points, errors = resolve_contours(geometry)
    if errors:
        return []
    costs = []
    for draw in geometry["draws"]:
        if draw["op"] == "fill":
            triangles = len(_triangulate_fill(points[draw["contour"]]))
        elif draw["op"] == "stroke":
            triangles = 0 if draw["widthPx"] == 0 else 3 * max(0, len(points[draw["contour"]]) - 1) + 2
        else:
            triangles = len(_band_triangles(points[draw["first"]], points[draw["second"]]))
        costs.append((triangles + 1) // 2)
    return costs


def contour_budget_errors(slots, available=MAX_DRAW_WORK_UNITS, prefix="$"):
    """Diagnose every excessive draw; earlier accepted capacity stays frozen."""
    from infini_local.core.schema_validation import strict_schema_errors

    consumed = 0
    errors = []
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict) or slot.get("rendererKind") != "contour":
            continue
        geometry = slot.get("geometry")
        if strict_schema_errors(geometry, contour_schema()):
            continue
        for draw_index, cost in enumerate(contour_draw_costs(geometry)):
            consumed += cost
            if cost > 0 and consumed > available:
                errors.append(
                    {
                        "path": f"{prefix}.slots[{index}].geometry.draws[{draw_index}]",
                        "message": f"contour composition exceeds available shared draw budget {available}; reduce this draw's demand; unrelated valid slots remain frozen",
                    }
                )
    return errors


def required_contour_budget(slots):
    from infini_local.core.schema_validation import strict_schema_errors

    return sum(
        sum(contour_draw_costs(slot["geometry"]))
        for slot in slots
        if isinstance(slot, dict)
        and slot.get("rendererKind") == "contour"
        and not strict_schema_errors(slot.get("geometry"), contour_schema())
    )
