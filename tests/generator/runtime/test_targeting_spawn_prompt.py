
"""Targeting guidance must use the same spawn syntax accepted by Author v5."""
import copy

from jsonschema import Draft202012Validator

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY


def test_targeting_spawn_example_matches_schema_without_admitting_retired_spelling():
    schema = CAPABILITY_REGISTRY["spawn"].provider_variant_schema()
    call = {
        "id": "child_spawn", "fn": "spawn", "target": "child",
        "params": {
            "velocity": {'speed': (8) * 60 / 16}, "count": 1,
            "spreadRadians": 0, 'offsetBlocks': (0) / 16, "aim": "velocity",
            "position": {"at": "activation_origin"},
        },
    }
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(call))
    retired = copy.deepcopy(call)
    del retired["params"]["position"]
    retired["params"]["placement"] = "item_use_origin"
    errors = list(validator.iter_errors(retired))
    assert {error.validator for error in errors} == {"additionalProperties", "required"}
