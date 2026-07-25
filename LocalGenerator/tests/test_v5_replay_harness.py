from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from typing import Any, cast

from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

_REPLAY_PATH = Path(__file__).resolve().parents[2] / "tools" / "replay_generation_case.py"
_SPEC = importlib.util.spec_from_file_location("infini_v5_replay_tool", _REPLAY_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
replay = cast(Any, _MODULE)


def _saved_case(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    item = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    replay._save_json(case_dir / "final_item.json", item)
    replay._save_json(case_dir / "compiled_runtime.json", replay._snapshot_for(item))
    return case_dir, item


def test_v5_replay_validates_wire_delivery_and_saved_snapshot(tmp_path) -> None:
    case_dir, _ = _saved_case(tmp_path)

    report = replay.build_replay_report(
        case_dir,
        compare=True,
        rerun=False,
        replay_raw=None,
    )

    assert report["ok"] is True
    assert [row["name"] for row in report["checks"]] == [
        "final_wire",
        "delivery_wire",
        "saved_snapshot",
    ]
    assert report["differences"] == []


def test_v5_replay_detects_executable_drift_and_unknown_wire_fields(tmp_path) -> None:
    case_dir, item = _saved_case(tmp_path)
    drifted = deepcopy(item)
    drifted["gameplay"]["damage"] += 1
    replay._save_json(case_dir / "final_item.json", drifted)

    drift_report = replay.build_replay_report(
        case_dir,
        compare=True,
        rerun=False,
        replay_raw=None,
    )
    assert drift_report["ok"] is False
    assert any(row["name"] == "saved_snapshot" for row in drift_report["checks"])
    assert any(row["path"].startswith("wire.gameplay.damage") for row in drift_report["differences"])

    invalid = deepcopy(item)
    invalid["runtimeProgram"]["entities"][0]["unknownFinalWireField"] = True
    replay._save_json(case_dir / "final_item.json", invalid)
    invalid_report = replay.build_replay_report(
        case_dir,
        compare=False,
        rerun=False,
        replay_raw=None,
    )
    assert invalid_report["ok"] is False
    assert invalid_report["checks"][0]["name"] == "strict_wire"
