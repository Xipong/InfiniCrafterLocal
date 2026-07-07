from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_replay_generation_case_summarizes_saved_artifacts(tmp_path: Path) -> None:
    case = tmp_path / "case_001"
    case.mkdir()
    (case / "parents.json").write_text(json.dumps([{"name": "A"}, {"name": "B"}]), encoding="utf-8")
    (case / "compiled_runtime.json").write_text(json.dumps({"patch": {}, "provenance": {"fieldSources": {"damage": "set_item_stats"}}}), encoding="utf-8")
    (case / "balance_report.json").write_text(json.dumps({"schema": "infini.balance-report.v1", "powerBand": "early", "clamps": {}}), encoding="utf-8")
    (case / "final_item.json").write_text(json.dumps({"name": "Replay Blade", "category": "weapon", "id": "abc"}), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "replay_generation_case.py"), str(case), "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    summary = json.loads(proc.stdout)
    assert summary["ok"] is True
    assert summary["dryRun"] is True
    assert summary["finalItem"]["name"] == "Replay Blade"
    assert summary["compiledRuntime"]["fieldSourceCount"] == 1
