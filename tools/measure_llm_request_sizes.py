#!/usr/bin/env python3
"""Measure real Author/Repair request builders and serializers, without inference.

Use --repo to compare a separate checkout with this one. Counts describe exact
JSON/text for synthetic offline fixtures, not billed tokens, latency or quality.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import socket
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    root = args.repo.resolve()
    sys.path.insert(0, str(root / "LocalGenerator"))

    from infini_local.core import llm_config
    from infini_local.core.llm_prompt_cache import PROMPT_CACHE_METADATA_KEY
    from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_program
    from infini_local.pipelines import llm_authoring_pipeline as author, llm_transport as transport
    from infini_local.pipelines.generated_parent_summary import attach_generated_parent_summary
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    from infini_local.services.codex_text_backend import _request_payload as codex_payload

    model = "gpt-6.1"  # Fixed route label only; no claim of live availability.
    contexts = {
        "chat_completions": {"provider": "openai_compat", "base_url": "https://api.openai.com/v1", "model": model, "api_mode": "chat_completions"},
        "responses": {"provider": "openai_compat", "base_url": "https://api.openai.com/v1", "model": model, "api_mode": "responses"},
        "codex_subscription": {"provider": "openai_codex", "model": model},
    }

    def compact(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def size(text):
        return {"chars": len(text), "utf8Bytes": len(text.encode("utf-8"))}

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Network/LLM inference is forbidden by this measurement")

    def wire(request, route):
        context = contexts[route]
        prepared = transport._payload_for_context(request, context)
        if route == "chat_completions":
            transport._cache_wire_options(prepared, request, context, api_mode=route)
            return prepared
        if route == "responses":
            return transport._responses_payload_from_chat(prepared, cache_source=request, context=context)
        if transport._prompt_cache_boundary(request) is not None:
            identity_source = {**prepared, PROMPT_CACHE_METADATA_KEY: request[PROMPT_CACHE_METADATA_KEY]}
            prepared["prompt_cache_key"] = transport._prompt_cache_identity(identity_source, model, context=context)
        return codex_payload(prepared)

    def measure(request):
        schema = (request.get("response_format") or {}).get("json_schema", {}).get("schema")
        return {
            "system": size(request["messages"][0]["content"]),
            "user": size(request["messages"][1]["content"]),
            "providerSchema": size(compact(schema)) if schema is not None else None,
            "staticUserPrefixChars": request.get(PROMPT_CACHE_METADATA_KEY, {}).get("prefixChars"),
            # These are the production http_json/post_sse default-space serializers.
            "httpBodies": {route: size(json.dumps(wire(request, route), ensure_ascii=False)) for route in contexts},
        }

    class Captured(BaseException):
        pass

    def capture_request(fn):
        requests = []

        def stop(request, **_kwargs):
            requests.append(copy.deepcopy(request))
            raise Captured()

        with patch.object(author, "llm_chat_json", stop):
            try:
                fn()
            except Captured:
                pass
        assert len(requests) == 1
        return requests[0]

    def generated_parent(name):
        authored = build_runtime_fixture(name)
        assert validate_runtime_program(authored)["ok"]
        data = compile_runtime_program(authored)
        data.update(id=f"audit_{name}", recipeKey=f"audit:{name}")
        attach_generated_parent_summary(data)
        return {"name": data["name"], "internalName": name, "sourceMod": "InfiniCrafterLocal", "generatedData": data}

    parent_a = {"id": "workbench", "name": "Workbench", "damage": 0, "useTime": 20, "tags": ["furniture"], "category": "placeable"}
    parent_b = {"id": "blade", "name": "Blade", "damage": 18, "useTime": 24, "tags": ["metal"], "category": "combat"}
    results = {"schema": "infini.offline-request-sizes.v1", "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
               "method": {"source": "real production builders and transport adapters", "inference": "notRun",
                          "fixtures": "synthetic existing fixtures, not captured live crafts",
                          "settings": {"modelRouteLabel": model, "promptStyle": "Default", "reasoning": "off; Author minimum medium still applies", "maxTokens": 9000},
                          "interpretation": "exact serialized characters/bytes; not billed tokens, speed or model quality"},
               "sourceFilesSha256": {}, "author": {}, "gameplayRepair": {}, "formatRepair": {}}
    for name in ("pipelines/llm_authoring_prompt.py", "pipelines/llm_authoring_pipeline.py", "pipelines/author_item_contract.py",
                 "core/runtime_authoring/program_schema.py", "core/runtime_authoring/repair_scope.py", "core/runtime_authoring/capability_registry.py"):
        results["sourceFilesSha256"][name] = hashlib.sha256((root / "LocalGenerator/infini_local" / name).read_bytes()).hexdigest()
    with ExitStack() as stack:
        for owner, values in [
            (socket, {"create_connection": forbidden, "getaddrinfo": forbidden}),
            (socket.socket, {"connect": forbidden, "connect_ex": forbidden}),
            (llm_config, {"PROMPT_STYLE": "Default"}),
            (transport, {"_primary_llm_context": lambda: contexts["chat_completions"], "LLM_REASONING_MODE": "off", "LLM_MAX_TOKENS": 9000,
                         "http_json": forbidden, "http_get_json": forbidden, "_perform_llm_http": forbidden}),
            (author, {"USE_LLM": True, "resolve_llm_model": lambda: model, "llm_chat_json": forbidden,
                      "trace_event": lambda *_a, **_kw: None, "trace_stage_request": lambda *_a, **_kw: None}),
        ]:
            for name, value in values.items():
                stack.enter_context(patch.object(owner, name, value))
        recipes = {
            "vanilla_tool_fixture": (parent_a, parent_b),
            "generated_plus_vanilla": (generated_parent("workbench_blade"), parent_b),
            "two_complex_generated": (generated_parent("held_and_deployed"), generated_parent("equipment_tool_combat")),
        }
        for label, (a, b) in recipes.items():
            results["author"][label] = {}
            for mode in ("json_object", "json_schema"):
                with patch.object(transport, "LLM_RESPONSE_FORMAT_MODE", mode):
                    request, _, _ = author.build_initial_author_request(a, b, {}, {}, label, model_name=model)
                    results["author"][label][mode] = measure(request)
                    if label == "vanilla_tool_fixture":
                        malformed = compact(build_runtime_fixture("workbench_blade"))[:-1]
                        format_request = capture_request(lambda: author._repair_malformed_author_json(
                            malformed_raw_text=malformed, parse_error=ValueError("missing final brace"),
                            original_recipe_context=request["messages"][1]["content"], model_name=model,
                            source_response_format=request.get("response_format"), recipe_key="audit_format_repair"))
                        results["formatRepair"][mode] = measure(format_request)
        broken = build_runtime_fixture("workbench_blade")
        next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == "configure_item_use")["params"].pop("useStyle")
        failure = validate_runtime_program(broken)
        assert not failure["ok"]
        for mode in ("json_object", "json_schema"):
            with patch.object(transport, "LLM_RESPONSE_FORMAT_MODE", mode):
                request = capture_request(lambda: author.repair_author_item_after_failure(
                    broken, parent_a, parent_b, {}, {}, "audit_repair", failure_report=failure))
                results["gameplayRepair"][mode] = measure(request)
    encoded = json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
