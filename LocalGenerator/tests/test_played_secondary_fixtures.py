"""Retained native input contracts; behavior lives in EngineRuntimeChecks.TooltipSecondaries."""
import copy
import json
from pathlib import Path

from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire


def test_played_secondary_native_inputs_preserve_exact_typed_events():
    root = Path(__file__).resolve().parents[2]
    rows = json.loads((root / "tools/fixtures/played-secondaries-delivered.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in rows}
    assert set(by_id) == {"g_4a1c8253fd834bff", "g_232a7838dccbe91d"}
    before = copy.deepcopy(rows)
    for row in rows:
        report = validate_runtime_wire(row)
        assert not report["ok"] and any(e["path"] == "$.runtimeProgram.itemUse.releaseTiming" for e in report["errors"])
        control = copy.deepcopy(row)
        assert control["gameplay"].pop("releaseTiming") == "immediate"
        assert control["runtimeProgram"]["itemUse"].pop("releaseTiming") == "immediate"
        assert control["runtimeProgram"]["itemUse"]["hideUseGraphic"] is True
        assert validate_runtime_wire(control)["ok"]
        assert control["runtimeProgram"]["entities"] == row["runtimeProgram"]["entities"]
    stone = by_id["g_4a1c8253fd834bff"]["runtimeProgram"]
    source = next(e for e in stone["entities"] if e["id"] == stone["primaryEntityId"])
    assert source["damage"]["damage"] == 10
    assert source["events"] == [dict(action="damage_area_on_event", actionCode=3,
        damageMultiplier=.5, delayTicks=10, event="on_hit", id="stonegel_delayed_splash", radiusPx=24)]
    ebon = by_id["g_232a7838dccbe91d"]["runtimeProgram"]
    source = next(e for e in ebon["entities"] if e["id"] == ebon["primaryEntityId"])
    event, = source["events"]
    assert (event["event"], event["actionCode"], event["count"], event["delayTicks"], event["damageBasis"], event["damageMultiplier"]) == (
        "on_hit", 1, 3, 0, "authored_child", 1)
    child = next(e for e in ebon["entities"] if e["id"] == event["entityId"])
    assert child["damage"]["damage"] == 3
    assert child["spawn"]["speedPxPerTick"] == 4
    assert child["movement"]["params"]["gravityPerTick"] == .18
    assert child["lifetimeTicks"] == 40

    assert rows == before


# These existing archives are byte authorities, not JSON-normalized golden outputs.
FROZEN_NATIVE_INPUTS = [
    ('LocalGenerator/tests/fixtures/persisted_v5_baseline.json', 'f34bc94a29038f341c46c227ba126a024e1f7ce711f4330a305f236ba579cefc'),
    ('tools/fixtures/played-silver-delivered.json', 'ebab278b44ec2938c0341f8c32c9fecf06e9ccb02fafebd8c4c2de5c27a5fda7'),
    ('tools/fixtures/played-secondaries-delivered.json', 'def06370b2d47cb11920972b6d60681046997afd199d97050cab60e7bcf5e8a5'),
    ('tools/fixtures/front-hand-compiled.json', 'dfcc7ce0cb1cbdf827b79c2d21b20de4e62edf2b26890ba74d509a56276ddc96'),
]


def test_frozen_native_inputs_survive_windows_checkout_without_normalizing_corruption(tmp_path):
    import hashlib
    import subprocess
    root = Path(__file__).resolve().parents[2]
    repo = tmp_path / 'checkout'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True,
                              capture_output=True, text=True, timeout=20)
    git('init', '-q')
    git('config', 'core.autocrlf', 'false')
    (repo / '.gitattributes').write_bytes((root / '.gitattributes').read_bytes())
    originals = {}
    for name, expected in FROZEN_NATIVE_INPUTS:
        original = (root / name).read_bytes()
        assert hashlib.sha256(original).hexdigest() == expected
        originals[name] = original
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original)
    git('add', '.')
    for autocrlf in ('true', 'false'):
        for name, _ in FROZEN_NATIVE_INPUTS:
            (repo / name).unlink()
        git('-c', 'core.autocrlf=' + autocrlf, 'checkout-index', '--all', '--force')
        for name, expected in FROZEN_NATIVE_INPUTS:
            checked_out = (repo / name).read_bytes()
            assert checked_out == originals[name]
            assert hashlib.sha256(checked_out).hexdigest() == expected
            # Even semantically harmless byte changes remain corruption to this contract.
            assert hashlib.sha256(checked_out + b' ').hexdigest() != expected
    # Negative control: Git's actual Windows conversion recreates the CI failure
    # without the archive-specific checkout contract; no manual JSON normalization.
    (repo / '.gitattributes').unlink()
    git('rm', '--cached', '.gitattributes')
    for name, _ in FROZEN_NATIVE_INPUTS:
        (repo / name).unlink()
    git('-c', 'core.autocrlf=true', 'checkout-index', '--all', '--force')
    for name, expected in FROZEN_NATIVE_INPUTS:
        converted = (repo / name).read_bytes()
        assert converted == originals[name].replace(b'\n', b'\r\n')
        assert hashlib.sha256(converted).hexdigest() != expected
