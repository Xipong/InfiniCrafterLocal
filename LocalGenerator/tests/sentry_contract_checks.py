"""Compare frozen pre-A6 bytes while asserting the complete declared delta."""
from copy import deepcopy


def without_declared_targeting_neutrals(compiled):
    result = deepcopy(compiled)
    expected = {"count": 1, "spreadRadians": 0.0, "targetPolicy": "distance_score",
                "requireLineOfSight": False, "hardRange": False}
    added_paths = set()
    for i, entity in enumerate(result["runtimeProgram"]["entities"]):
        targeting = entity.get("targeting")
        if not targeting:
            continue
        for name, value in expected.items():
            assert targeting[name] == value and type(targeting[name]) is type(value)
            targeting.pop(name)
            added_paths.add(f"runtimeProgram.entities[{i}].targeting.{name}")
    contract = result.get("runtimeContract")
    if contract:
        rows = contract["finalWireReceipts"]
        added = [row for row in rows if row["finalPath"] in added_paths]
        assert {row["finalPath"] for row in added} == added_paths
        for row in added:
            assert row["fn"] == "target_and_fire" and row["status"] == "declared_neutral_omission"
            assert row["value"] == expected[row["finalPath"].rsplit(".", 1)[1]]
        contract["finalWireReceipts"] = [row for row in rows if row["finalPath"] not in added_paths]
    return result
