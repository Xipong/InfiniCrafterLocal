"""Offline transactions: real Repair, PNG assessment and campaign consumer seams.

Case tables own every changed value and failure policy. These helpers do not
invent authored fields, replace validators, or authenticate synthetic art.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import (
    apply_repair_patch, build_runtime_repair_scope, validate_runtime_program,
)
from infini_local.pipelines import visual_delivery_gate
from infini_local.services import asset_sync_service


def frozen_json(value):
    """Type- and presence-sensitive closure, ignoring object insertion order only."""
    return json.dumps(value, sort_keys=True)


class RepairTransaction:
    """One broken source, canonical report/scope and separately authored patch."""
    def __init__(self, current, errors=None, *, report=None, scope=None):
        self.current = current
        self.before = frozen_json(current)
        self.report = validate_runtime_program(current) if report is None else report
        if errors is None:
            assert not self.report["ok"], self.report
            errors = self.report["errors"]
        assert errors, "an explicitly supplied boundary report must not be empty"
        self.scope = build_runtime_repair_scope(current, errors) if scope is None else scope

    def apply(self, patch, *, accepted=True):
        from infini_local.core.runtime_authoring import filter_repair_patch_scope

        patch_before = frozen_json(patch)
        filtered, audit = filter_repair_patch_scope(self.current, patch, self.scope)
        assert audit["ok"] is accepted, audit
        repaired = apply_repair_patch(self.current, filtered)
        if accepted:
            assert validate_runtime_program(repaired)["ok"]
        assert frozen_json(self.current) == self.before, "Repair mutated the broken input"
        assert frozen_json(patch) == patch_before, "Repair mutated the proposed patch"
        return repaired, filtered, audit


@pytest.fixture(autouse=True)
def isolated_serving_roots(monkeypatch, tmp_path):
    """Temporary assets still go through the production filename-serving owner."""
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", tmp_path / "world-recipes")


@pytest.fixture
def png_assessments(monkeypatch):
    from infini_local.pipelines import sprite_postprocess

    calls = Counter()
    real = asset_sync_service.is_complete_png_file

    def counted(path):
        calls[Path(path).resolve()] += 1
        return real(path)

    monkeypatch.setattr(asset_sync_service, "is_complete_png_file", counted)
    monkeypatch.setattr(sprite_postprocess, "is_complete_png_file", counted)
    return calls


def selected_pngs(data):
    paths = [visual_delivery_gate._resolved_asset_path(name)
             for name in asset_sync_service.runtime_asset_files(data)]
    assert all(path is not None for path in paths)
    return {path.resolve() for path in paths if path is not None}


def install_campaign_fault(monkeypatch, *, boundary, consumer, change):
    """Inject at the actual projector or captured production gate, not a QA alias."""
    from infini_local.pipelines import combine_pipeline
    from infini_local.qa import live_no_image_fixture as qa

    visited = []
    if boundary == "projection":
        original = qa.FunctionType

        def wrap(code, globals_, *args):
            project = original(code, globals_, *args)

            def projected(control):
                change()
                visited.append("projection")
                return project(control)

            return projected

        monkeypatch.setattr(qa, "FunctionType", wrap)
    elif boundary == "after_projection":
        original = qa.synthetic_no_image_execution_control

        def projected(*args):
            control = original(*args)
            change()
            visited.append("after_projection")
            return control

        monkeypatch.setattr(qa, "synthetic_no_image_execution_control", projected)
    attr = "assert_visual_delivery_ready" if consumer == "early" else "_cached_payload_report"
    gate = getattr(combine_pipeline, attr)

    def consumed(control):
        if boundary in {"before_gate", "serving_selection"}:
            change()
        result = gate(control)
        if consumer == "final":
            assert result["ok"], "fault setup must leave a healthy production read"
        visited.append("gate")
        if boundary == "after_gate":
            change()
        return result

    monkeypatch.setattr(combine_pipeline, attr, consumed)
    return visited
