"""Explicit canonical Codex campaign owner; historical no-image runner stays separate."""
from __future__ import annotations

from argparse import Namespace
from collections import Counter
from collections.abc import Callable
from contextlib import AbstractContextManager
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any
import uuid

from toolbox.live.budget import budget_status, finish_attempt, reserve_attempt
from toolbox.live.panels import load_case_input_payloads, load_selection
from toolbox.live.support import (
    FROZEN_LLM_STAGES, author_stage, expected_stage_max_tokens,
    expected_stage_temperature, response_format_type, valid_author_call_budget,
)

_ACTIVE_CASE: ContextVar[dict[str, Any] | None] = ContextVar('real_campaign_case', default=None)


def write_json(path: Path, value: Any) -> None:
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def case_payload(case_id: str, item_a: dict[str, Any], item_b: dict[str, Any]) -> dict[str, Any]:
    # Subset order/index is deliberately not part of world identity.
    digest = hashlib.sha256(case_id.encode('utf-8')).digest()
    return {'itemA': item_a, 'itemB': item_b,
            'worldId': 910000 + int.from_bytes(digest[:4], 'big') % 1_000_000_000,
            'worldName': 'QA_Real_' + case_id}


class PhysicalAccounting:
    """Metadata-only observer at the existing canonical physical-send boundary."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.events: list[dict[str, Any]] = []
        self.stream_events: Counter[str] = Counter()
        self.write_failed = False

    def observe(self, row: dict[str, Any]) -> None:
        # The production observer deliberately swallows observer errors. Persist
        # that loss locally and fail the receipt rather than claim full accounting.
        try:
            event = row.get('event')
            with self.lock:
                if event == 'sse_event':
                    self.stream_events[str(row.get('eventType', 'unknown'))] += 1
                    return
                if event not in {'request', 'post_start', 'http_response', 'attempt_end', 'call_end'}:
                    return
                kept = {key: row[key] for key in (
                    'transportCallId', 'endpoint', 'method', 'physicalAttemptIndex',
                    'physicalAttemptCount', 'networkStarted', 'reason', 'httpStatus',
                    'openMs', 'readMs', 'elapsedMs', 'terminal', 'outcome', 'errorType',
                    'event', 'observedAt', 'startedAt',
                ) if key in row}
                self.events.append(kept)
                with self.path.open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps(kept, ensure_ascii=False) + '\n')
        except Exception:
            self.write_failed = True

    def summary(self) -> dict[str, Any]:
        starts = [row for row in self.events if row['event'] == 'post_start']
        calls = {row.get('transportCallId') for row in self.events if row['event'] in {'request', 'post_start'}}
        started_attempts = {(str(row.get('transportCallId')), int(row.get('physicalAttemptIndex', 1))) for row in starts}
        ended_attempts = {(str(row.get('transportCallId')), int(row.get('physicalAttemptIndex', 1)))
            for row in self.events if row['event'] == 'attempt_end'}
        ended = {row.get('transportCallId') for row in self.events if row['event'] == 'call_end'}
        return {
            'physicalTextPosts': sum(str(row.get('endpoint', '')).endswith('/responses') for row in starts),
            'physicalImagePosts': sum(str(row.get('endpoint', '')).endswith('/images/generations') for row in starts),
            'physicalOtherPosts': sum(not str(row.get('endpoint', '')).endswith(('/responses', '/images/generations')) for row in starts),
            'transportRetryPosts': sum(row.get('reason') == 'transport_retry' or int(row.get('physicalAttemptIndex', 1)) > 1 for row in starts),
            'unfinishedCalls': sorted(str(value) for value in calls - ended),
            'unfinishedPhysicalAttempts': [list(value) for value in sorted(started_attempts - ended_attempts)],
            'failedAttempts': sum(row.get('event') == 'attempt_end' and row.get('outcome') == 'failure' for row in self.events),
            'streamEventCounts': dict(self.stream_events),
            'observationWriteFailed': self.write_failed,
        }


def execute_case(case_id: str, item_a: dict[str, Any], item_b: dict[str, Any], *, output: Path,
                 budget_path: Path, combine_call: Callable[[dict[str, Any]], dict[str, Any]],
                 observation_scope: Callable[[dict[str, Any], Callable[[dict[str, Any]], None]], AbstractContextManager[Any]],
                 exact_input: dict[str, Any] | None = None, require_zero_transport_retries: bool = False) -> dict[str, Any]:
    directory = output / 'cases' / case_id
    directory.mkdir(parents=True, exist_ok=False)
    payload = case_payload(case_id, item_a, item_b)
    if exact_input is not None:
        blob = Path(exact_input['path']).read_bytes()
        if hashlib.sha256(blob).hexdigest() != exact_input['sha256']:
            raise ValueError('exact native input changed after admission')
        payload = json.loads(blob)
        if payload.get('itemA') != item_a or payload.get('itemB') != item_b:
            raise ValueError('exact input parent snapshots changed')
        with (directory / 'source_input.json').open('xb') as handle:
            handle.write(blob)
    write_json(directory / 'input.json', payload)
    attempt_id = uuid.uuid4().hex
    admission = reserve_attempt(budget_path, attempt_id=attempt_id, case_id=case_id, kind='full_craft')
    write_json(directory / 'admission.json', admission)
    accounting = PhysicalAccounting(directory / 'physical.ndjson')
    logical: list[dict[str, Any]] = []
    token = _ACTIVE_CASE.set({'directory': directory, 'logical': logical, 'lock': threading.Lock()})
    started = time.monotonic()
    receipt: dict[str, Any] = {'case': case_id, 'attemptId': attempt_id, 'kind': 'full_craft', 'ok': False,
        'sourceInputSha256': exact_input['sha256'] if exact_input else None,
        'requireZeroTransportRetries': require_zero_transport_retries}
    try:
        with observation_scope({'case': case_id, 'attemptId': attempt_id}, accounting.observe):
            result = combine_call(payload)
        write_json(directory / 'final_item.json', result)
        receipt['finalSha256'] = hashlib.sha256((directory / 'final_item.json').read_bytes()).hexdigest()
        receipt['ok'] = True
    except Exception as exc:
        # Provider diagnostics remain in the canonical secret-redacting trace.
        receipt['errorType'] = type(exc).__name__
    finally:
        _ACTIVE_CASE.reset(token)
        receipt.update(accounting.summary())
        receipt['logicalStages'] = dict(Counter(str(row['stage']) for row in logical if row['event'] == 'request'))
        receipt['authorCallBudgetValid'] = valid_author_call_budget(
            initial_calls=receipt['logicalStages'].get('initial_author', 0),
            repair_calls=receipt['logicalStages'].get('scoped_repair', 0))
        receipt['firstAuthorSuccess'] = (receipt['ok'] and receipt['logicalStages'].get('initial_author') == 1
            and receipt['logicalStages'].get('scoped_repair', 0) == 0)
        receipt['elapsedSeconds'] = round(time.monotonic() - started, 3)
        receipt['requiredStagesObserved'] = all(receipt['logicalStages'].get(stage, 0) >= 1
            for stage in ('initial_author', 'visual_director', 'vfx_director'))
        if (receipt['unfinishedCalls'] or receipt['unfinishedPhysicalAttempts'] or receipt['observationWriteFailed'] or receipt['physicalOtherPosts']
                or receipt['physicalTextPosts'] < 3 or receipt['physicalImagePosts'] < 1
                or not receipt['requiredStagesObserved'] or not receipt['authorCallBudgetValid']
                or (require_zero_transport_retries and receipt['transportRetryPosts'] > 0)):
            receipt['ok'] = False
        receipt['firstAuthorSuccess'] = receipt['firstAuthorSuccess'] and receipt['ok']
        write_json(directory / 'receipt.json', receipt)
        finish_attempt(budget_path, attempt_id=attempt_id, receipt=receipt)
    return receipt


def validate_logical_request(payload: dict[str, Any], args: Namespace) -> str:
    stage = author_stage(payload)
    if stage not in FROZEN_LLM_STAGES or payload.get('model') != args.expected_model:
        raise ValueError('unclassified stage or model drift in real campaign')
    expected_temperature = expected_stage_temperature(stage, director_temperature=args.expected_temperature,
        repair_temperature=args.expected_repair_temperature, vfx_director_temperature=args.expected_vfx_temperature)
    if expected_temperature is not None and payload.get('temperature') != expected_temperature:
        raise ValueError('logical stage temperature drift')
    expected_tokens = expected_stage_max_tokens(stage, author_tokens=args.expected_max_tokens,
        visual_tokens=args.expected_visual_max_tokens, vfx_tokens=args.expected_vfx_max_tokens)
    token_budget = payload.get('max_tokens', payload.get('max_completion_tokens', payload.get('max_output_tokens')))
    if expected_tokens is not None and token_budget != expected_tokens:
        raise ValueError('logical stage answer budget drift')
    reasoning = payload.get('reasoning') or {}
    efforts = [payload['reasoning_effort']] if 'reasoning_effort' in payload else []
    if isinstance(reasoning, dict) and 'effort' in reasoning:
        efforts.append(reasoning['effort'])
    if not efforts or any(effort != args.expected_reasoning_effort for effort in efforts) or response_format_type(payload) != args.expected_response_format:
        raise ValueError('logical reasoning effort or response format drift')
    return stage


def validate_projected_text_request(url: str, payload: dict[str, Any], args: Namespace) -> None:
    if url != 'https://chatgpt.com/backend-api/codex/responses':
        raise ValueError('projected text request escaped canonical endpoint')
    if payload.get('model') != args.expected_model or (payload.get('reasoning') or {}).get('effort') != args.expected_reasoning_effort:
        raise ValueError('projected text model or reasoning drift')
    if ((payload.get('text') or {}).get('format') or {}).get('type') != args.expected_response_format:
        raise ValueError('projected response format drift')


def run(args: Namespace, preflight: dict[str, Any], environment: dict[str, str]) -> int:
    """Called only after explicit read-only admission and --run."""
    if not args.run or not args.real_images:
        raise ValueError('real campaign execution needs explicit --real-images --run')
    if 'infini_local.core.config_bootstrap' in sys.modules:
        raise RuntimeError('real campaign requires a fresh process before production configuration imports')
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('real campaign output is not empty')
    os.environ.update(environment)
    os.environ.update({
        'INFINI_SKIP_CONFIG_FILE': '1', 'INFINI_CACHE_DIR': str(output / 'cache'),
        'INFINI_WORLD_RECIPES_DIR': str(output / 'cache' / 'world_recipes'),
        'INFINI_SDCPP_SERVER_AUTOSTART': '0', 'INFINI_TRACE_PROMPTS': '1',
        'INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK': '0',
    })
    sys.path.insert(0, str(Path(preflight['project']) / 'LocalGenerator'))
    from infini_local.pipelines.transport import client, http as text_http
    from infini_local.services import codex_auth, codex_image_backend

    original_chat = client.llm_chat_json
    original_image = codex_image_backend.generate_image
    original_post_sse = codex_auth.post_sse
    original_http_json = text_http.http_json

    def chat(payload: dict[str, Any], timeout: int = 10):
        stage = validate_logical_request(payload, args)
        state = _ACTIVE_CASE.get()
        if state is None:
            raise RuntimeError('unreserved logical request')
        with state['lock']:
            number = len(state['logical']) + 1
            state['logical'].append({'stage': stage, 'event': 'request'})
        write_json(state['directory'] / f'logical-{number:03d}-request.json', payload)
        return original_chat(payload, timeout=timeout)

    def image(prompt: str, negative: str, output_path: Path, *, model: str, quality: str, size: str, timeout: int, background: str = 'opaque') -> None:
        if _ACTIVE_CASE.get() is None:
            raise RuntimeError('unreserved image request')
        if (model, quality, size) != (args.expected_image_model, args.expected_image_quality, args.expected_image_size):
            raise ValueError('image model/quality/size drift')
        return original_image(prompt, negative, output_path, model=model, quality=quality, size=size,
                              timeout=timeout, background=background)

    def post_sse(url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None,
                 timeout: float = 120, limit: int = 8 * 1024 * 1024) -> dict[str, Any]:
        validate_projected_text_request(url, payload, args)
        state = _ACTIVE_CASE.get()
        if state is None:
            raise RuntimeError('unreserved projected text request')
        with state['lock']:
            number = state.get('wireSequence', 0) + 1
            state['wireSequence'] = number
        write_json(state['directory'] / f'wire-{number:03d}-request.json', payload)
        return original_post_sse(url, payload, headers=headers, timeout=timeout, limit=limit)

    def forbidden_compat_http(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError('non-Codex text HTTP is forbidden in this real campaign')

    client.llm_chat_json = chat
    text_http.http_json = forbidden_compat_http
    codex_auth.post_sse = post_sse
    codex_image_backend.generate_image = image
    try:
        # Import after wrapping the canonical entrypoints; no asset-sync, image,
        # validation, cache or world-storage stubs. All storage roots are private.
        from infini_local.pipelines.combine_pipeline import combine
        _, _, selected, source_path, _, _ = load_selection(args)
        exact_inputs = load_case_input_payloads(Path(source_path), selected)
        for case_id, ref in exact_inputs.items():
            if preflight.get('exactInputs', {}).get(case_id, {}).get('sha256') != ref['sha256']:
                raise ValueError('exact input changed between preflight and execution')
        write_json(output / 'campaign_manifest.json', {
            **preflight, 'schema': 'infini.real-campaign.v1',
            'projectionLimits': 'Codex projects logical temperature/output-token budgets away; they are not wire cost caps.',
            'imageRetries': args.image_retries, 'stageOnly': False,
            'sourceRecovery': 'Reconstructed runner; historical tested tree/evidence not reproduced.',
        })
        receipts = [execute_case(case_id, a, b, output=output,
            budget_path=args.attempt_budget.expanduser().resolve(), combine_call=combine,
            observation_scope=codex_auth.generation_observations, exact_input=exact_inputs.get(case_id),
            require_zero_transport_retries=args.require_zero_transport_retries) for case_id, a, b in selected]
        first_author = sum(row['firstAuthorSuccess'] for row in receipts)
        summary = {'schema': 'infini.real-campaign-summary.v1', 'ok': all(row['ok'] for row in receipts) and first_author >= args.min_first_author,
            'firstAuthorSuccesses': first_author, 'requiredFirstAuthorSuccesses': args.min_first_author,
            'realImageGeneration': True, 'cases': receipts,
            'attemptBudget': budget_status(args.attempt_budget.expanduser().resolve()),
            'scope': 'Canonical pipeline and physical-call accounting, not native gameplay or art acceptance.'}
        write_json(output / 'summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        return 0 if summary['ok'] else 1
    finally:
        client.llm_chat_json = original_chat
        codex_image_backend.generate_image = original_image
        codex_auth.post_sse = original_post_sse
        text_http.http_json = original_http_json
