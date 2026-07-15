from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
import json
from pathlib import Path
import sys
import threading
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines import llm_transport as transport


def _chat_payload(stage: str) -> dict:
    return {
        "model": "ignored",
        "messages": [
            {"role": "system", "name": f"{stage}_contract", "content": f"{stage} instructions"},
            {"role": "user", "name": f"{stage}_context", "content": '{"currentItem":{"name":"Probe"}}'},
        ],
        "max_tokens": 321,
        "response_format": {"type": "json_object"},
    }


def _contract_check_item_lease_round_robin_pins_every_call_to_one_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        transport,
        "LLM_POOL_PROFILES",
        (
            {"id": "llm_2", "enabled": True, "provider": "openai_compat", "base_url": "https://two.example/v1", "api_key": "two", "model": "model-two", "api_mode": "chat_completions"},
            {"id": "llm_3", "enabled": True, "provider": "openai_compat", "base_url": "https://three.example/v1", "api_key": "three", "model": "model-three", "api_mode": "chat_completions"},
        ),
    )
    monkeypatch.setattr(transport, "LLM_PROVIDER", "openai_compat")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_BASE_URL", "https://one.example/v1")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_API_KEY", "one")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_MODEL", "model-one")
    monkeypatch.setattr(transport, "LLM_API_MODE", "chat_completions")
    transport._reset_llm_pool_runtime_for_tests()

    calls: list[tuple[str, str]] = []

    def fake_http_json(url, payload, timeout=10, headers=None):
        calls.append((url, payload["model"]))
        return {"choices": [{"message": {"role": "assistant", "content": "{}"}}]}

    monkeypatch.setattr(transport, "http_json", fake_http_json)

    selected: list[str] = []
    for recipe in ("r1", "r2", "r3", "r4"):
        with transport.llm_item_lease(recipe) as lease:
            selected.append(lease.profile_id)
            transport.llm_chat_json(_chat_payload("visual_director"), timeout=1)
            transport.llm_chat_json(_chat_payload("vfx_director"), timeout=1)

    assert selected == ["llm_1", "llm_2", "llm_3", "llm_1"]
    assert [url.split("//", 1)[1].split(".", 1)[0] for url, _ in calls] == [
        "one", "one", "two", "two", "three", "three", "one", "one",
    ]


def _contract_check_responses_chain_and_stateless_chat_fallback_use_full_stage_dossier(monkeypatch) -> None:
    monkeypatch.setattr(transport, "LLM_POOL_PROFILES", ())
    monkeypatch.setattr(transport, "LLM_PROVIDER", "openai_compat")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_BASE_URL", "https://responses.example/v1")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_API_KEY", "key")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_MODEL", "model-r")
    monkeypatch.setattr(transport, "LLM_API_MODE", "auto")
    transport._reset_llm_pool_runtime_for_tests()

    bodies: list[tuple[str, dict]] = []

    def fake_http_json(url, payload, timeout=10, headers=None):
        bodies.append((url, payload))
        if url.endswith("/responses"):
            response_number = sum(1 for seen_url, _ in bodies if seen_url.endswith("/responses"))
            return {
                "id": f"resp_{response_number}",
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
                "usage": {"input_tokens": 100, "output_tokens": 5, "input_tokens_details": {"cached_tokens": 40}},
            }
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(transport, "http_json", fake_http_json)

    with transport.llm_item_lease("responses-chain"):
        first = transport.llm_chat_json(_chat_payload("visual_director"), timeout=1)
        second = transport.llm_chat_json(_chat_payload("vfx_director"), timeout=1)

    assert first["choices"][0]["message"]["content"] == "{}"
    assert second["_debug"]["previousResponseId"] == "resp_1"
    first_body = bodies[0][1]
    second_body = bodies[1][1]
    assert first_body["instructions"] == "visual_director instructions"
    assert first_body["input"][0]["content"] == '{"currentItem":{"name":"Probe"}}'
    assert "previous_response_id" not in first_body
    assert second_body["previous_response_id"] == "resp_1"
    assert second["_debug"]["cachedInputTokens"] == 40

    transport._reset_llm_pool_runtime_for_tests()
    fallback_bodies: list[tuple[str, dict]] = []

    def unsupported_responses(url, payload, timeout=10, headers=None):
        fallback_bodies.append((url, payload))
        if url.endswith("/responses"):
            raise urllib.error.HTTPError(url, 404, "not found", hdrs=Message(), fp=None)
        return {"choices": [{"message": {"role": "assistant", "content": "{}"}}]}

    monkeypatch.setattr(transport, "http_json", unsupported_responses)
    dossier = _chat_payload("visual_director")
    with transport.llm_item_lease("responses-fallback"):
        result = transport.llm_chat_json(dossier, timeout=1)

    assert result["_debug"]["apiMode"] == "chat_completions"
    assert [url.rsplit("/", 1)[-1] for url, _ in fallback_bodies] == ["responses", "completions"]
    assert fallback_bodies[-1][1]["messages"] == dossier["messages"]


def _contract_check_responses_server_failure_uses_profile_failover_without_chat_downgrade(monkeypatch) -> None:
    monkeypatch.setattr(
        transport,
        "LLM_POOL_PROFILES",
        (
            {"id": "llm_2", "enabled": True, "provider": "openai_compat", "base_url": "https://two.example/v1", "api_key": "two", "model": "model-two", "api_mode": "auto"},
        ),
    )
    monkeypatch.setattr(transport, "LLM_PROVIDER", "openai_compat")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_BASE_URL", "https://primary.example/v1")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_API_KEY", "one")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_MODEL", "primary-model")
    monkeypatch.setattr(transport, "LLM_API_MODE", "auto")
    transport._reset_llm_pool_runtime_for_tests()
    calls: list[str] = []

    def fake_http_json(url, payload, timeout=10, headers=None):
        calls.append(url)
        if "primary.example" in url:
            raise urllib.error.HTTPError(url, 503, "provider unavailable", Message(), None)
        if url.endswith("/responses"):
            return {
                "id": "resp_secondary",
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
            }
        raise AssertionError(f"unexpected stateless downgrade: {url}")

    monkeypatch.setattr(transport, "http_json", fake_http_json)
    with transport.llm_item_lease("responses-provider-failover") as lease:
        result = transport.llm_chat_json(_chat_payload("visual_director"), timeout=1)
        assert result["_debug"]["apiMode"] == "responses"
        assert lease.profile_id == "llm_2"

    assert calls == [
        "https://primary.example/v1/responses",
        "https://two.example/v1/responses",
    ]



def _contract_check_provider_failure_switches_current_item_to_next_profile_and_pins_it(monkeypatch):
    monkeypatch.setattr(
        transport,
        "LLM_POOL_PROFILES",
        (
            {"id": "llm_2", "enabled": True, "provider": "openai_compat", "base_url": "https://two.example/v1", "api_key": "two", "model": "model-two", "api_mode": "chat_completions"},
        ),
    )
    monkeypatch.setattr(transport, "LLM_PROVIDER", "openai_compat")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_BASE_URL", "https://primary.example/v1")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_API_KEY", "one")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_MODEL", "primary-model")
    monkeypatch.setattr(transport, "LLM_API_MODE", "chat_completions")
    transport._reset_llm_pool_runtime_for_tests()
    calls: list[str] = []

    def fake_http_json(url, payload, timeout=10, headers=None):
        calls.append(url)
        if "primary.example" in url:
            raise urllib.error.HTTPError(url, 503, "flaky provider", Message(), None)
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(transport, "http_json", fake_http_json)
    with transport.llm_item_lease("failover-item") as lease:
        result = transport.llm_chat_json(_chat_payload("visual_director"), timeout=1)
        assert result["choices"][0]["message"]["content"] == "{}"
        assert lease.profile_id == "llm_2"
        assert lease.failovers == [
            {"fromProfileId": "llm_1", "toProfileId": "llm_2", "reason": "HTTPError"}
        ]
        transport.llm_chat_json(_chat_payload("vfx_director"), timeout=1)
        assert lease.profile_id == "llm_2"

    assert calls == [
        "https://primary.example/v1/chat/completions",
        "https://two.example/v1/chat/completions",
        "https://two.example/v1/chat/completions",
    ]
    assert transport._PROFILE_COOLDOWN_UNTIL["llm_1"] > 0


def _contract_check_concurrent_item_leases_isolate_sequence_profile_and_response_chain(monkeypatch) -> None:
    monkeypatch.setattr(
        transport,
        "LLM_POOL_PROFILES",
        (
            {"id": "llm_2", "enabled": True, "provider": "openai_compat", "base_url": "https://two.example/v1", "api_key": "two", "model": "model-two", "api_mode": "responses"},
            {"id": "llm_3", "enabled": True, "provider": "openai_compat", "base_url": "https://three.example/v1", "api_key": "three", "model": "model-three", "api_mode": "responses"},
        ),
    )
    monkeypatch.setattr(transport, "LLM_PROVIDER", "openai_compat")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_BASE_URL", "https://one.example/v1")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_API_KEY", "one")
    monkeypatch.setattr(transport, "OPENAI_COMPAT_MODEL", "model-one")
    monkeypatch.setattr(transport, "LLM_API_MODE", "responses")
    transport._reset_llm_pool_runtime_for_tests()

    worker_count = 12
    barrier = threading.Barrier(worker_count)
    call_lock = threading.Lock()
    chains: dict[str, list[str]] = {}
    profile_calls: dict[str, list[str]] = {}

    def fake_http_json(url, payload, timeout=10, headers=None):
        assert url.endswith("/responses")
        recipe = str(json.loads(payload["input"][0]["content"])["recipe"])
        previous = str(payload.get("previous_response_id") or "")
        with call_lock:
            chain = chains.setdefault(recipe, [])
            chain.append(previous)
            ordinal = len(chain)
            profile_calls.setdefault(recipe, []).append(url)
        expected_previous = "" if ordinal == 1 else f"resp_{recipe}_1"
        assert previous == expected_previous
        return {
            "id": f"resp_{recipe}_{ordinal}",
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
        }

    monkeypatch.setattr(transport, "http_json", fake_http_json)

    def run_item(index: int) -> dict[str, object]:
        recipe = f"concurrent_{index}"
        assert transport.current_llm_item_lease() is None
        with transport.llm_item_lease(recipe) as lease:
            assert transport.current_llm_item_lease() is lease
            barrier.wait(timeout=5)
            payload = _chat_payload("visual_director")
            payload["messages"][1]["content"] = json.dumps({"recipe": recipe})
            transport.llm_chat_json(payload, timeout=1)
            transport.llm_chat_json(payload, timeout=1)
            inside_snapshot = lease.snapshot()
            result = {
                "recipe": recipe,
                "leaseId": lease.lease_id,
                "profileId": lease.profile_id,
                "callCount": inside_snapshot["callCount"],
                "stages": inside_snapshot["stages"],
            }
        result["cleanAfter"] = transport.current_llm_item_lease() is None
        return result

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        results = list(pool.map(run_item, range(worker_count)))

    lease_ids = [str(row["leaseId"]) for row in results]
    assert len(set(lease_ids)) == worker_count
    assert sorted(int(lease_id.rsplit(":", 1)[1]) for lease_id in lease_ids) == list(range(1, worker_count + 1))
    assert Counter(str(row["profileId"]) for row in results) == Counter({"llm_1": 4, "llm_2": 4, "llm_3": 4})
    assert all(row["callCount"] == 2 and len(row["stages"]) == 2 and row["cleanAfter"] for row in results)
    assert all(chain == ["", f"resp_{recipe}_1"] for recipe, chain in chains.items())
    assert all(len(set(urls)) == 1 for urls in profile_calls.values())
    assert transport.current_llm_item_lease() is None

    try:
        with transport.llm_item_lease("exception_cleanup"):
            raise RuntimeError("synthetic parser failure")
    except RuntimeError as exc:
        assert str(exc) == "synthetic parser failure"
    assert transport.current_llm_item_lease() is None


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_246_llm_pool_responses_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_item_lease_round_robin_pins_every_call_to_one_profile',
            '_contract_check_responses_chain_and_stateless_chat_fallback_use_full_stage_dossier',
            '_contract_check_responses_server_failure_uses_profile_failover_without_chat_downgrade',
            '_contract_check_provider_failure_switches_current_item_to_next_profile_and_pins_it',
            '_contract_check_concurrent_item_leases_isolate_sequence_profile_and_response_chain',
        ),
    )
