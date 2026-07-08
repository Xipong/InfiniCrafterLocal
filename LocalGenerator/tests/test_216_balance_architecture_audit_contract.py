from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "LocalGenerator"
sys.path.insert(0, str(LOCAL))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_llm_prompt_no_longer_receives_parent_relative_soft_balance_caps():
    authoring = read(LOCAL / "infini_local" / "pipelines" / "llm_authoring_pipeline.py")
    prompt_owner = read(LOCAL / "infini_local" / "pipelines" / "llm_authoring_prompt.py")
    prompt_surface = authoring + prompt_owner
    parent_context = read(LOCAL / "infini_local" / "pipelines" / "parent_context_pipeline.py")
    contracts = read(LOCAL / "infini_local" / "core" / "contract_versions.py")

    assert "source_power_envelope_for_prompt" not in authoring
    assert "source_power_envelope_for_prompt" not in parent_context
    assert "sourceEnvelope" not in prompt_surface
    assert "softDamageCapPerHit" not in prompt_surface
    assert "softAoeTilesCap" not in prompt_surface
    assert "softActiveProjectileCap" not in prompt_surface
    assert "balancePolicy" in prompt_surface
    assert "python_post_authoring_soft_envelope" in prompt_surface
    assert "prompt_free_parent_soft_caps_code_owned_balance_audit_v0.4.216" in contracts
    assert "balanceArchitectureAuditContract" in contracts


def test_payload_exposes_hard_engine_ranges_but_not_dynamic_balance_numbers():
    from infini_local.pipelines.llm_authoring_pipeline import build_llm_author_payload

    item_a = {"name": "Copper Shortsword", "damage": 5, "useTime": 13, "rare": 0, "value": 100}
    item_b = {"name": "Star Wrath", "damage": 170, "useTime": 16, "rare": 10, "value": 1000000}
    payload = build_llm_author_payload(item_a, item_b, {}, {}, "audit-key")
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    assert payload["validatorRanges"]["damage"] == [0, 999]
    assert "balancePolicy" in payload
    assert payload["engineRuntimeContract"]["validatorLimits"]["balanceAuthority"] == "python_post_authoring_soft_envelope"
    assert "softDamageCapPerHit" not in text
    assert "sourceEnvelope" not in text
    assert "terrariaProgressionReference" not in text


def test_balance_doc_describes_layer_boundaries():
    doc = read(ROOT / "docs" / "BALANCE_REFERENCE_VANILLA_PROGRESS_LIMITS_RU.md")
    assert "LLM author" in doc
    assert "Python post-authoring balance" in doc
    assert "Runtime compiler clamps" in doc
    assert "C# hard safety" in doc
    assert "softDamageCapPerHit" in doc  # mentioned only as removed, not active code
    assert "больше не передаются" in doc
