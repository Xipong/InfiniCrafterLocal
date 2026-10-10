"""Compare frozen pre-A7 bytes after proving the complete neutral extension delta."""
from copy import deepcopy


def without_declared_beam_neutrals(compiled):
    result = deepcopy(compiled)
    expected = {"manaPayment": "initial_use_only", "initialDamageMultiplier": 1.0,
                "initialWidthMultiplier": 1.0, "damageStartProgress": 1.0, "raycastTiles": False}
    added_paths = set()
    for i, entity in enumerate(result["runtimeProgram"]["entities"]):
        controller = entity.get("controller", {})
        if controller.get("name") != "channel_beam":
            continue
        for name, value in expected.items():
            params = controller["params"]
            assert params[name] == value and type(params[name]) is type(value)
            params.pop(name)
            added_paths.add(f"runtimeProgram.entities[{i}].controller.params.{name}")
    contract = result.get("runtimeContract")
    if contract:
        rows = contract["finalWireReceipts"]
        added = [row for row in rows if row["finalPath"] in added_paths]
        assert len(added) == len(added_paths) and {row["finalPath"] for row in added} == added_paths
        for row in added:
            assert row["fn"] == "channel_beam" and row["status"] == "declared_neutral_omission"
            assert row["value"] == expected[row["finalPath"].rsplit(".", 1)[1]]
        contract["finalWireReceipts"] = [row for row in rows if row["finalPath"] not in added_paths]
    return result
