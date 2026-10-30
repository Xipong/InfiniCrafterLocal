"""Recursive Author notation preserves validation and execution facts, not wire schema."""
import copy

from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY, ParamSpec, author_parameter_shape,
)


def test_nested_card_has_one_requiredness_notation_without_changing_schema_or_literals():
    numeric = ParamSpec(kind="number", description="Rate", minimum=-2, maximum=8,
                        exclusive_minimum=-1, multiple_of=0.25, units="pixels/update",
                        required=False, default=3, neutral=0)
    required_neutral = ParamSpec(kind="integer", description="Required count", minimum=0,
                                 maximum=5, neutral=0)
    branch = ParamSpec(kind="object", description="Branch", properties={"rate": numeric, "count": required_neutral}, min_properties=1)
    spec = ParamSpec(kind="union", description="Choose", alternatives=(branch, ParamSpec(kind="string", description="Stop", enum=("stop",))))
    schema = spec.schema()
    before = copy.deepcopy(schema)
    result = author_parameter_shape(schema)
    assert result == {
        "meaning": "Choose", "oneOf": [
            {"type": "object", "meaning": "Branch", "minProperties": 1,
             "additionalProperties": False, "properties": {
                 "rate": {"type": "number", "meaning": "Rate", "min": -2, "max": 8,
                          "exclusiveMinimum": -1, "multipleOf": 0.25, "units": "pixels/update",
                          "optional": True, "default": 3, "neutral": 0},
                 "count": {"type": "integer", "meaning": "Required count", "min": 0, "max": 5, "neutral": 0}}},
            {"type": "string", "meaning": "Stop", "enum": ["stop"]}]}
    assert schema == before == spec.schema()


def test_parameter_shape_does_not_rewrite_literal_projection_metadata():
    schema = {"type": "number", "x-infini-authorProjection": {
        "required": ["wire"], "properties": {"description": "literal"},
        "wireProjection": {"multiplier": 60, "divisor": 16, "updatePower": 2},
        "rounding": "nearest_world_tick_half_up"},
        "default": {"description": "literal", "minimum": 7}}
    before = copy.deepcopy(schema)
    result = author_parameter_shape(schema)
    assert result["projectionConstraints"] == schema["x-infini-authorProjection"]
    assert result["default"] == schema["default"]
    result["projectionConstraints"]["required"].append("changed")
    assert schema == before


def test_strict_scalar_peak_bounds_are_visible_not_only_prose():
    for name in ("front_arm_pose", "set_projectile_reach_curve"):
        card = CAPABILITY_REGISTRY[name].author_prompt_card()["params"]["peakProgress"]
        if "paramRef" in card:
            owner, param = card["paramRef"].split(".")
            card = CAPABILITY_REGISTRY[owner].author_prompt_card()["params"][param]
        assert card["exclusiveMinimum"] == 0
        assert card["exclusiveMaximum"] == 1


def test_composed_required_names_and_additional_property_schema_preserve_validation():
    from jsonschema import Draft202012Validator
    schema = {"type": "object", "properties": {"x": {"type": "integer"}},
              "required": ["x", "y"],
              "allOf": [{"properties": {"y": {"type": "number", "minimum": 2}}}],
              "additionalProperties": {"type": "number", "maximum": 10}}
    projected = author_parameter_shape(schema)
    assert projected["required"] == ["y"]
    assert projected["additionalProperties"] == {"type": "number", "max": 10}

    def restore(node):
        result = {}
        for key, value in node.items():
            if key == "optional":
                continue
            if key == "properties":
                result[key] = {name: restore(child) for name, child in value.items()}
            elif key == "allOf":
                result[key] = [restore(child) for child in value]
            elif key == "additionalProperties" and isinstance(value, dict):
                result[key] = restore(value)
            else:
                result[{"min": "minimum", "max": "maximum"}.get(key, key)] = value
        if "properties" in node:
            required = list(result.get("required", []))
            required += [name for name, child in node["properties"].items() if not child.get("optional", False)]
            result["required"] = required
        return result

    decoded = restore(projected)
    for instance in ({}, {"x": 1}, {"y": 2}, {"x": 1, "y": 2},
                     {"x": 1, "y": 1}, {"x": 1, "y": 11},
                     {"x": 1, "y": 2, "z": 3}, {"x": 1, "y": 2, "z": 12}):
        assert Draft202012Validator(schema).is_valid(instance) == Draft202012Validator(decoded).is_valid(instance)
