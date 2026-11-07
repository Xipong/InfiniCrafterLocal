"""Final delivery name rules must reject or Repair in Gameplay, before art work."""
from __future__ import annotations

import pytest
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.pipelines.author.stage import authored_item_validation_report, strict_validate_authored_item
from infini_local.pipelines.final_normalize import final_normalize
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


@pytest.mark.parametrize(
    ("name", "parent_a", "parent_b", "rejected"),
    [
        ("AB", "Tin Sword", "Stone", True),  # Schema permits 1-2 chars, final does not.
        ("Generated Blade", "Tin Sword", "Stone", True),
        ("Infini-Blade", "Tin Sword", "Stone", True),
        ("combined armor", "Tin Sword", "Stone", True),
        ("object", "Tin Sword", "Stone", True),
        ("Tin Sword", "Tin Sword", "Stone", True),
        ("tIN sWORD", "Tin Sword", "Stone", True),
        ("Twin", "Twin", "Twin", True),  # Equal parent names are not an exemption.
        ("Aether Spear", "Tin Sword", "Stone", False),
        ("GeneratedSword", "Tin Sword", "Stone", False),  # Only reserved prefix forms.
    ],
)
def test_gameplay_name_admission_matches_final_delivery(
    name: str, parent_a: str, parent_b: str, rejected: bool
) -> None:
    authored = build_runtime_fixture("workbench_blade")
    authored["name"] = name
    left, right = {"name": parent_a}, {"displayName": parent_b}
    report = authored_item_validation_report(authored, left, right)
    identity = [row for row in report["errors"] if row["path"] == "$.name"
                and row["code"] == "uncombined_identity"]
    assert bool(identity) is rejected, report["errors"]

    delivery = {"name": name, "parentA": parent_a, "parentB": parent_b}
    if rejected:
        with pytest.raises(PlannerUnavailable, match="Gameplay Author low-level runtime rejected") as exc:
            strict_validate_authored_item(authored, left, right)
        assert identity[0] in exc.value.author_repair_targets
        scope = build_runtime_repair_scope(authored, report["errors"])
        assert scope["metadataFields"] == ["name"], "the normal scoped Gameplay Repair must own this name"
        with pytest.raises(PlannerUnavailable, match="final result name is invalid"):
            final_normalize(delivery)
    else:
        assert report["ok"], report["errors"]
        assert strict_validate_authored_item(authored, left, right) is authored
        assert final_normalize(delivery)["name"] == name
