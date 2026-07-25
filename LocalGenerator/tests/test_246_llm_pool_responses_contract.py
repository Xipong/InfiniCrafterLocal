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
    finite_stage = {
        "item_author_contract": "planner",
        "runtime_repair": "author_repair",
        "visual_director": "visual_director",
        "vfx_director": "vfx_director",
    }[stage]
    return transport.with_llm_stage({
        "model": "ignored",
        "messages": [
            {"role": "system", "name": f"{stage}_contract", "content": f"{stage} instructions"},
            {"role": "user", "name": f"{stage}_context", "content": '{"currentItem":{"name":"Probe"}}'},
        ],
        "max_tokens": 321,
        "response_format": {"type": "json_object"},
    }, finite_stage)


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
    dossier["reasoning"] = {"effort": "low"}
    dossier[transport.LLM_MODEL_OVERRIDE_KEY] = "replacement-model"
    with transport.llm_item_lease("responses-fallback"):
        result = transport.llm_chat_json(dossier, timeout=1)

    assert result["_debug"]["apiMode"] == "chat_completions"
    footprint = result["_debug"]["transportFootprint"]
    assert set(footprint) == {
        "mode", "responseMode", "provider", "profile", "systemChars", "systemTokensEstimate",
        "userChars", "userTokensEstimate", "schemaChars", "schemaTokensEstimate",
        "repairChars", "repairTokensEstimate", "totalChars", "totalTokensEstimate",
    }
    assert footprint["mode"] == "visual_director"
    assert footprint["responseMode"] == "json_object"
    assert footprint["provider"] == "openai_compat"
    assert footprint["profile"] == "llm_1"
    assert footprint["systemChars"] > 0 and footprint["userChars"] > 0
    assert footprint["systemTokensEstimate"] > 0 and footprint["userTokensEstimate"] > 0
    assert footprint["repairChars"] == 0 and footprint["totalChars"] > footprint["userChars"]
    repair_footprint = transport._transport_footprint(_chat_payload("runtime_repair"), "author_repair")
    assert repair_footprint["userChars"] == 0 and repair_footprint["repairChars"] > 0
    assert result["_debug"]["transportRetryCount"] == 1
    assert result["_debug"]["transportRetryCauses"] == ["responses_to_chat_fallback"]
    assert [url.rsplit("/", 1)[-1] for url, _ in fallback_bodies] == ["responses", "completions"]
    assert "text" in fallback_bodies[0][1]
    assert fallback_bodies[0][1]["reasoning"] == {"effort": "low"}
    assert fallback_bodies[0][1]["model"] == "replacement-model"
    assert transport.LLM_MODEL_OVERRIDE_KEY not in fallback_bodies[0][1]
    assert fallback_bodies[-1][1]["messages"] == dossier["messages"]
    assert fallback_bodies[-1][1]["response_format"] == dossier["response_format"]
    assert fallback_bodies[-1][1]["reasoning"] == dossier["reasoning"]
    assert fallback_bodies[-1][1]["model"] == "replacement-model"
    assert transport.LLM_MODEL_OVERRIDE_KEY not in fallback_bodies[-1][1]


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
    calls: list[tuple[str, dict]] = []

    def fake_http_json(url, payload, timeout=10, headers=None):
        calls.append((url, payload))
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
    request_payload = _chat_payload("visual_director")
    request_payload[transport.LLM_MODEL_OVERRIDE_KEY] = "replacement-model"
    with transport.llm_item_lease("responses-provider-failover") as lease:
        result = transport.llm_chat_json(request_payload, timeout=1)
        assert result["_debug"]["apiMode"] == "responses"
        assert lease.initial_profile_id == "llm_1"
        assert lease.profile_id == "llm_2"
        second_request = _chat_payload("item_author_contract")
        second_request[transport.LLM_MODEL_OVERRIDE_KEY] = "replacement-model"
        second_result = transport.llm_chat_json(second_request, timeout=1)
        assert second_result["_debug"]["apiMode"] == "responses"
        assert lease.snapshot()["initialProfileId"] == "llm_1"
        assert lease.profile_id == "llm_2"

    assert [url for url, _ in calls] == [
        "https://primary.example/v1/responses",
        "https://two.example/v1/responses",
        "https://two.example/v1/responses",
    ]
    assert [body["model"] for _, body in calls] == ["replacement-model", "model-two", "model-two"]
    assert all(transport.LLM_MODEL_OVERRIDE_KEY not in body for _, body in calls)



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


def _contract_check_remote_rate_limiter_is_shared_token_aware_and_429_safe(monkeypatch) -> None:
    clock = [1000.0]
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(round(float(seconds), 3))
        clock[0] += float(seconds)

    monkeypatch.setattr(transport.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(transport.time, "sleep", fake_sleep)
    body = b"x" * 20_000  # 5K estimated tokens.
    gemini = {"model": "gemini-3.1-flash-lite"}
    url = "https://provider.example/v1/chat/completions"

    transport._reset_llm_pool_runtime_for_tests()
    for _ in range(4):
        transport._reserve_remote_rate_slot(url, gemini, body)
    assert sleeps == [12.0, 12.0, 36.0]
    assert sum(count for _, count in transport._LLM_RATE_STATE[next(iter(transport._LLM_RATE_STATE))]["events"]) == 15_000

    transport._reset_llm_pool_runtime_for_tests()
    sleeps.clear()
    gemma = {"model": "gemma-3-27b"}
    transport._reserve_remote_rate_slot(url, gemma, b"{}")
    transport._reserve_remote_rate_slot(url, gemma, b"{}")
    assert sleeps == [62.0]

    transport._reset_llm_pool_runtime_for_tests()
    sleeps.clear()
    transport._reserve_remote_rate_slot("http://127.0.0.1:8085/v1/chat/completions", gemini, body)
    transport._reserve_remote_rate_slot("http://localhost:1234/v1/chat/completions", gemini, body)
    assert sleeps == []
    assert transport._LLM_RATE_STATE == {}

    transport._reset_llm_pool_runtime_for_tests()
    sleeps.clear()
    headers = Message()
    headers["Retry-After"] = "75"
    error = urllib.error.HTTPError(url, 429, "rate limited", headers, None)
    transport._mark_remote_rate_limited(url, gemini, error)
    transport._reserve_remote_rate_slot(url, gemini, b"{}")
    assert sleeps == [75.0]


# One collected item per contract module; local checks are discovered in source order.
def test_246_llm_pool_responses_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request)
