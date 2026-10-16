#!/usr/bin/env python3
"""Capture real offline stage requests and exact serialized provider HTTP bodies.

Run in a fresh process for each --repo (including immutable baseline trees).
Uses the repository's current QA/test fixtures; requires its test dependencies.
No inference, credentials, model discovery or network is permitted. Token counts,
when a local tiktoken vocabulary is available, are named proxies, never billing.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import inspect
import json
import os
import socket
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

MODEL = "gpt-6.1"
STAGES = ("author", "visual", "vfx", "gameplay_repair", "visual_repair", "vfx_repair", "format_repair")
MODES = ("json_object", "json_schema")
ROUTES = ("chat_completions", "responses", "codex_subscription")
COHORT = ("vanilla_tool_fixture", "generated_plus_vanilla", "two_complex_generated")


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def forbidden(*_args, **_kwargs):
    raise AssertionError("Network/inference forbidden by offline packet capture")


class Captured(BaseException):
    """Escape production Exception handlers without inventing a model response."""


def dossier(request):
    """Derived semantic view only; measured packets always retain original rows."""
    pieces = [json.loads(row["content"]) for row in request["messages"][1:]]
    merged = {}
    for piece in pieces:
        assert not merged.keys() & piece.keys()
        merged.update(piece)
    definitions = merged.pop("schemaDefinitions", {}).get("$defs", {})

    def inline(node):
        if isinstance(node, dict):
            if set(node) == {"$ref"} and node["$ref"].startswith("#/$defs/"):
                name = node["$ref"][len("#/$defs/"):]
                if name in definitions:
                    return inline(definitions[name])
            return {key: inline(value) for key, value in node.items()}
        if isinstance(node, list):
            return [inline(value) for value in node]
        return node

    return inline(merged)


class OfflineCapture:
    """Production builders -> production sender -> serialized urllib Request."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        sys.dont_write_bytecode = True
        sys.path[:0] = [str(self.root / "LocalGenerator"), str(self.root / "LocalGenerator/tests")]
        from infini_local.core import llm_config, vfx_manifest
        from infini_local.core.runtime_authoring.compiler import compile_runtime_program
        from infini_local.core.runtime_authoring.validator import validate_runtime_program
        from infini_local.pipelines import llm_authoring_pipeline, llm_transport, visual_generation_pipeline, vfx_generation_pipeline
        from infini_local.pipelines.generated_parent_summary import attach_generated_parent_summary
        from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
        from infini_local.services import codex_auth
        from test_low_level_three_stage_pipeline import _visual_kit
        from vfx_material_fixtures import _legacy
        self.config, self.vfx = llm_config, vfx_manifest
        self.author, self.transport = llm_authoring_pipeline, llm_transport
        self.visual, self.vfx_sender = visual_generation_pipeline, vfx_generation_pipeline
        self.compile, self.validate, self.fixture = compile_runtime_program, validate_runtime_program, build_runtime_fixture
        self.attach_parent, self.auth = attach_generated_parent_summary, codex_auth
        self.visual_fixture, self.vfx_fixture = _visual_kit, _legacy
        self.contexts = {
            route: {"provider": "openai_codex" if route == "codex_subscription" else "openai_compat",
                    "base_url": "https://chatgpt.com/backend-api/codex" if route == "codex_subscription" else "https://api.openai.com/v1",
                    "api_mode": "chat_completions" if route == "chat_completions" else "responses",
                    "model": MODEL, "api_key": "offline"}
            for route in ROUTES
        }

    def __enter__(self):
        self.stack = ExitStack()
        settings = [
            (socket, {"create_connection": forbidden, "getaddrinfo": forbidden}),
            (socket.socket, {"connect": forbidden, "connect_ex": forbidden}),
            (self.config, {"PROMPT_STYLE": "Default"}),
            (self.transport, {"_primary_llm_context": lambda: self.contexts["chat_completions"],
                              "LLM_REASONING_MODE": "off", "LLM_MAX_TOKENS": 9000,
                              "CODEX_VISUAL_REASONING": "inherit",
                              "_llm_replay_json_response": lambda *_: None,
                              "_reserve_remote_rate_slot": lambda *_a, **_kw: None,
                              "urlopen_no_redirect": forbidden, "http_get_json": forbidden}),
            (self.auth, {"get_credentials": lambda: SimpleNamespace(access_token="offline", account_id="offline"),
                         "_generation_request": forbidden}),
        ]
        for owner in (self.author, self.visual, self.vfx_sender):
            values = {"resolve_llm_model": lambda: MODEL, "llm_chat_json": forbidden}
            for name in ("USE_LLM", "trace_event", "trace_stage_request"):
                if hasattr(owner, name):
                    values[name] = True if name == "USE_LLM" else lambda *_a, **_kw: None
            settings.append((owner, values))
        for owner, values in settings:
            for name, value in values.items():
                self.stack.enter_context(patch.object(owner, name, value))
        self.recipes = self._recipes()
        return self

    def __exit__(self, *exc):
        return self.stack.__exit__(*exc)

    def _recipes(self):
        def parent(name):
            authored = self.fixture(name)
            assert self.validate(authored)["ok"]
            data = self.compile(authored)
            data.update(id=f"audit_{name}", recipeKey=f"audit:{name}")
            self.attach_parent(data)
            return {"name": data["name"], "internalName": name, "sourceMod": "InfiniCrafterLocal", "generatedData": data}
        a = {"id": "workbench", "name": "Workbench", "damage": 0, "useTime": 20, "tags": ["furniture"], "category": "placeable"}
        b = {"id": "blade", "name": "Blade", "damage": 18, "useTime": 24, "tags": ["metal"], "category": "combat"}
        return {
            COHORT[0]: (a, b, "workbench_blade"),
            COHORT[1]: (parent("workbench_blade"), b, "held_and_deployed"),
            COHORT[2]: (parent("held_and_deployed"), parent("equipment_tool_combat"), "equipment_tool_combat"),
        }

    def stage_inputs(self, cohort):
        a, b, fixture = copy.deepcopy(self.recipes[cohort])
        authored = self.fixture(fixture)
        assert self.validate(authored)["ok"]
        data = self.compile(authored)
        data.update(id="audit_" + fixture, recipeKey=cohort)
        kit = self.visual_fixture(data)
        # The canonical fixture omits overlay when not requested; add the existing
        # test overlay design only for a runtime that actually requires one.
        from infini_local.pipelines.visual_asset_plan import equipment_overlay_requirement
        if equipment_overlay_requirement(data)["required"] and "equipOverlay" not in kit:
            kit["equipOverlay"] = {"prompt": "badge", "silhouette": "badge", "visualIdentity": "badge", "preferredCanvasSize": 32}
        runtime = data["runtimeProgram"]
        ids = [row["id"] for row in runtime["entities"]]
        accepted, errors = self.visual._validate_kit(kit, ids, runtime["itemEntityId"],
            equipment_overlay_required=bool(equipment_overlay_requirement(data)["required"]))
        assert accepted is not None, errors
        visual_data = self.visual._apply_kit(copy.deepcopy(data), accepted)
        raw_vfx = self.vfx_fixture(visual_data)
        # Use the selected checkout's actual supported fixture without translating
        # historical manifests or filling current fields.
        report = self.vfx.validate_vfx_director_output(raw_vfx, visual_data)
        assert report["ok"], report["errors"]
        return {"parentA": a, "parentB": b, "authored": authored, "data": data,
                "visualKit": kit, "visualData": visual_data, "vfxOutput": raw_vfx,
                "sourceVfxFixture": self.vfx_fixture(visual_data)}

    def _invoke(self, fn, *args, **kwargs):
        # This audit runs unchanged against immutable before/after checkouts.
        # Historical argument slots are not part of current application code.
        names = tuple(inspect.signature(fn).parameters)
        if "ca" in names:
            offset = names.index("ca")
            args = (*args[:offset], {}, {}, *args[offset:])
        return fn(*args, **kwargs)

    def builder(self, stage, cohort, mode):
        self.transport.LLM_RESPONSE_FORMAT_MODE = mode
        inputs = self.stage_inputs(cohort)
        a, b, authored, data = [inputs[key] for key in ("parentA", "parentB", "authored", "data")]
        requests = []
        evidence = {"fixture": self.recipes[cohort][2], "inputs": copy.deepcopy(inputs)}

        def stop(request, **_kwargs):
            requests.append(copy.deepcopy(request))
            raise Captured()

        with ExitStack() as stack:
            for owner in (self.author, self.visual, self.vfx_sender):
                stack.enter_context(patch.object(owner, "llm_chat_json", stop))
            try:
                if stage == "author":
                    self._invoke(self.author.try_llm_plan, a, b, cohort)
                elif stage == "format_repair":
                    source, context, _ = self._invoke(self.author.build_initial_author_request, a, b, cohort, model_name=MODEL)
                    malformed = compact(authored)[:-1]
                    evidence.update(malformedRawText=malformed)
                    self.author._repair_malformed_author_json(malformed_raw_text=malformed,
                        parse_error=ValueError("missing final brace"), original_recipe_context=context,
                        model_name=MODEL, source_response_format=source.get("response_format"), recipe_key=cohort)
                elif stage == "gameplay_repair":
                    broken = copy.deepcopy(authored)
                    next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == "configure_item_use")["params"].pop("useStyle")
                    report = self.validate(broken)
                    assert not report["ok"]
                    evidence.update(broken=broken, failureReport=report)
                    self._invoke(self.author.repair_author_item_after_failure, broken, a, b, cohort, failure_report=report)
                elif stage.startswith("visual"):
                    kwargs = {}
                    if stage.endswith("repair"):
                        broken = copy.deepcopy(inputs["visualKit"])
                        broken["item"]["renderSizePx"] = None
                        runtime = data["runtimeProgram"]
                        ids = [row["id"] for row in runtime["entities"]]
                        _, errors = self.visual._validate_kit(broken, ids, runtime["itemEntityId"])
                        assert errors
                        scope = self.visual._build_visual_repair_scope(broken, errors, ids, runtime["itemEntityId"])
                        evidence.update(broken=broken, errors=errors, repairScope=scope)
                        kwargs = dict(repair_errors=errors, previous=broken, repair_scope=scope)
                    self._invoke(self.visual._request_visual_kit, data, a, b, **kwargs)
                elif stage.startswith("vfx"):
                    kwargs = {}
                    if stage.endswith("repair"):
                        broken = copy.deepcopy(inputs["vfxOutput"])
                        broken["slots"][0]["alpha"] = 2.0
                        report = self.vfx.validate_vfx_director_output(broken, inputs["visualData"])
                        assert not report["ok"]
                        scope = self.vfx._build_vfx_repair_scope(broken, report["errors"])
                        evidence.update(broken=broken, errors=report["errors"], repairScope=scope)
                        kwargs = dict(repair_errors=report["errors"], previous=broken, repair_scope=scope)
                    self.vfx._request(self.vfx_sender.call_llm_vfx_director,
                        self.vfx._prompt_packet(inputs["visualData"], a, b), **kwargs)
                else:
                    raise ValueError(stage)
            except Captured:
                pass
        assert len(requests) == 1, (stage, len(requests))
        return requests[0], evidence

    def wire(self, request, route):
        """Intercept actual bytes after the production HTTP/SSE serializer."""
        captured = []
        before = copy.deepcopy(request)

        def stop(req, **_kwargs):
            captured.append({"url": req.full_url, "method": req.get_method(),
                             "body": req.data.decode("utf-8"), "packet": json.loads(req.data)})
            raise Captured()

        with patch.object(self.transport, "urlopen_no_redirect", stop), patch.object(self.auth, "_generation_request", stop):
            try:
                self.transport._llm_json_single_context(request, 10, self.contexts[route])
            except Captured:
                pass
        assert len(captured) == 1, (route, len(captured))
        assert request == before, "Provider projection mutated builder packet"
        return captured[0]


def tokenizer_status():
    status = {"installed": {name: importlib.util.find_spec(name) is not None
                           for name in ("tiktoken", "tokenizers", "transformers")},
              "proxy": None, "note": "Uses only an already cached vocabulary; no download during capture, never billed tokens."}
    encode = None
    if status["installed"]["tiktoken"]:
        try:
            import tiktoken
            # Vocabulary access is also network-guarded. Only cached data works.
            encoder = tiktoken.get_encoding("o200k_base")
            encode = lambda text: len(encoder.encode(text, disallowed_special=()))
            status["proxy"] = "tiktoken:o200k_base on exact text (not chat framing/billing)"
        except Exception as exc:
            status["unavailableReason"] = f"{type(exc).__name__}: {exc}"
    return status, encode


def size(text, encode=None):
    result = {"unicodeChars": len(text), "utf8Bytes": len(text.encode("utf-8"))}
    if encode:
        result["tokenProxy"] = encode(text)
    return result


def measurements(request, wire, encode=None):
    rows = request["messages"]
    fields = dossier(request)
    cache = request.get("_infini_prompt_cache", {})
    boundary = cache.get("staticDataMessageIndex", cache.get("instructionMessageIndex", 0))
    packet = wire["packet"]
    response = packet.get("response_format", packet.get("text", {}).get("format"))
    provider_schema = (response.get("json_schema", response).get("schema") if isinstance(response, dict) else None)
    json_size = lambda value: size(compact(value), encode) if value is not None else None
    return {
        "httpBody": size(wire["body"], encode),
        "messages": [{"index": i, "role": row["role"], "content": size(row["content"], encode),
                      "segment": "system" if i == 0 else "static" if i <= boundary else "dynamic"}
                     for i, row in enumerate(rows)],
        "staticContent": size("".join(row["content"] for row in rows[:boundary + 1]), encode),
        "dynamicContent": size("".join(row["content"] for row in rows[boundary + 1:]), encode),
        "providerInlineSchemaCompact": json_size(provider_schema),
        "responseWrapperCompact": json_size(response),
        "toolsCompact": json_size(packet.get("tools")),
        "parentContextFieldsCompact": {key: json_size(value) for key, value in fields.items()
            if key in {"parents", "parentFactsReadOnly", "originalRecipeContext", "sourceWireUnits"}},
        "repairPermissionsCompact": json_size(fields.get("repairScope", {}).get("fieldPermissions")),
        "note": "Component JSON uses compact separators; content is literal. Components overlap; only HTTP bodies are additive.",
    }


def compare(current, baseline):
    old = {row["id"]: row for row in baseline["captures"]}
    assert set(old) == {row["id"] for row in current["captures"]}, "Comparison cohorts differ"
    rows = []
    metric_keys = tuple(key for key in ("unicodeChars", "utf8Bytes", "tokenProxy")
                        if key in current["captures"][0]["sizes"]["httpBody"]
                        and key in baseline["captures"][0]["sizes"]["httpBody"])
    for row in current["captures"]:
        before = old[row["id"]]["sizes"]["httpBody"]
        after = row["sizes"]["httpBody"]
        rows.append({"id": row["id"], "before": before, "after": after,
                     "delta": {key: after[key] - before[key] for key in metric_keys}})
    return {"baselineHead": baseline["head"], "captures": rows,
            "aggregate": {key: {"before": sum(row["before"][key] for row in rows),
                                "after": sum(row["after"][key] for row in rows),
                                "delta": sum(row["delta"][key] for row in rows)}
                          for key in metric_keys}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True, help="Size/index JSON; full packets saved alongside")
    parser.add_argument("--compare", type=Path, help="Previously captured baseline index (never rebuilt from candidate imports)")
    args = parser.parse_args()
    # Set before any application imports; never read operator config.env, touch
    # source caches, or inherit replay/live route settings into the fixture run.
    for key in list(os.environ):
        if key.startswith("INFINI_"):
            os.environ.pop(key)
    os.environ.update({"INFINI_SKIP_CONFIG_FILE": "1", "INFINI_USE_LLM": "0",
                       "INFINI_SDCPP_SERVER_AUTOSTART": "0"})
    sandbox = tempfile.TemporaryDirectory(prefix="infini-request-measure-")
    os.environ.update({"INFINI_CACHE_DIR": str(Path(sandbox.name) / "cache"),
                       "INFINI_WORLD_RECIPES_DIR": str(Path(sandbox.name) / "world")})
    root, out = args.repo.resolve(), args.out.resolve()
    packet_dir = out.with_suffix("").with_name(out.stem + "-packets")
    assert not out.exists() and not packet_dir.exists(), "Use new output paths; captures are append-only evidence"
    packet_dir.mkdir(parents=True)
    result = {"schema": "infini.offline-stage-packets.v2", "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "repo": str(root), "sourceFilesSha256": {}, "captures": [],
              "method": {"source": "production stage senders and production serialized urllib Requests",
                         "network": "forbidden", "inference": "notRun", "credentials": "offline placeholders, headers excluded",
                         "fixtures": "existing QA runtime fixtures and canonical visual/VFX test helpers; deterministic synthetic inputs, not live outputs",
                         "settings": {"modelRouteLabel": MODEL, "promptStyle": "Default", "reasoning": "off, Author minimum medium", "maxTokens": 9000, "codexVisualReasoning": "inherit"},
                         "cohort": list(COHORT), "stages": list(STAGES), "formats": list(MODES), "routes": list(ROUTES),
                         "envelope": "Exact HTTP JSON body bytes after production serialization; excludes URL/headers/TLS. Static/dynamic literal message content and compact component JSON are overlapping diagnostics, not additive token costs."}}
    # Hash imported production and fixture files after capture too: concurrent
    # edits must not silently produce a mixed-version before/after result.
    sources = list((root / "LocalGenerator/infini_local").rglob("*.py")) + [
        root / "LocalGenerator/tests/test_low_level_three_stage_pipeline.py", root / "LocalGenerator/tests/vfx_material_fixtures.py"]
    hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    with OfflineCapture(root) as capture:
        result["tokenizer"], encode = tokenizer_status()
        for cohort in COHORT:
            for mode in MODES:
                for stage in STAGES:
                    request, evidence = capture.builder(stage, cohort, mode)
                    ident = f"{cohort}.{mode}.{stage}"
                    builder_path = packet_dir / (ident + ".builder.json")
                    builder_path.write_text(json.dumps({"request": request, "evidence": evidence}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    for route in ROUTES:
                        wire = capture.wire(request, route)
                        path = packet_dir / (ident + "." + route + ".http-body.json")
                        path.write_bytes(wire["body"].encode("utf-8"))
                        result["captures"].append({"id": ident + "." + route, "cohort": cohort, "stage": stage,
                            "mode": mode, "route": route, "url": wire["url"], "method": wire["method"],
                            "builderFile": str(builder_path.relative_to(out.parent)), "bodyFile": str(path.relative_to(out.parent)),
                            "bodySha256": hashlib.sha256(wire["body"].encode()).hexdigest(), "sizes": measurements(request, wire, encode)})
    assert hashes == {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}, "Source changed during capture; rerun with a fresh output path"
    result["sourceFilesSha256"] = hashes
    metric_keys = ("unicodeChars", "utf8Bytes", "tokenProxy") if encode else ("unicodeChars", "utf8Bytes")
    result["totals"] = {route: {mode: {"captures": len(rows := [row for row in result["captures"] if row["route"] == route and row["mode"] == mode]),
        **{key: sum(row["sizes"]["httpBody"][key] for row in rows) for key in metric_keys}}
        for mode in MODES} for route in ROUTES}
    result["stageTotals"] = {route: {mode: {stage: {
        "captures": len(rows := [row for row in result["captures"] if row["route"] == route and row["mode"] == mode and row["stage"] == stage]),
        **{key: {"total": sum(values := [row["sizes"]["httpBody"][key] for row in rows]),
                   "min": min(values), "mean": sum(values) / len(values), "max": max(values)}
           for key in metric_keys}}
        for stage in STAGES} for mode in MODES} for route in ROUTES}
    result["aggregate"] = {"captures": len(result["captures"]),
        **{key: sum(row["sizes"]["httpBody"][key] for row in result["captures"]) for key in metric_keys},
        "interpretation": "Sum over the entire fixture/format/provider comparison matrix, not one craft; conditional repairs are all forced independently."}
    if args.compare:
        result["comparison"] = compare(result, json.loads(args.compare.read_text(encoding="utf-8")))
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"index": str(out), "packets": len(result["captures"]), "tokenizer": result["tokenizer"], "totals": result["totals"],
                      "comparison": result.get("comparison", {}).get("aggregate")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
