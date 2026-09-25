from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
import traceback
from typing import Any, cast

TOOLBOX = Path(__file__).resolve().parents[1]
if str(TOOLBOX) not in sys.path:
    sys.path.insert(0, str(TOOLBOX))
from infini_toolbox import discover_project, load_config_env, new_run_dir  # noqa: E402
parser = argparse.ArgumentParser(
    description="Run real InfiniCrafter LLM generation while hard-blocking every image backend call."
)
parser.add_argument("--project", type=Path, help="Authoritative InfiniCrafterLocal worktree.")
parser.add_argument("--output", type=Path, help="Trace directory; defaults to artifacts/tool-runs.")
parser.add_argument("--cases", help="Comma-separated built-in case IDs; default runs the fixed acceptance 20.")
parser.add_argument(
    "--cases-file",
    type=Path,
    help="JSON case set with {case,itemA,itemB} dump identities; default uses the fixed acceptance 20.",
)
parser.add_argument(
    "--runtime-dump", type=Path,
    help="Parent item JSONL; defaults to the bundled exact Terraria fixture in toolbox/fixtures.",
)
parser.add_argument("--expected-case-count", type=int, help="Require the selected case count before network.")
parser.add_argument("--transport-retries", type=int, default=0, help="Explicit retries per case for confirmed network failures only.")
parser.add_argument(
    "--transport-retry-delay-seconds", type=int, default=60,
    help="Minimum wait after a network failure before retrying that case; at least 60 seconds.",
)
parser.add_argument("--expected-provider", help="Fail before network if the configured provider differs.")
parser.add_argument("--expected-model", help="Fail before network or per request if the exact model differs.")
parser.add_argument("--expected-base-url", help="Require the exact configured OpenAI-compatible endpoint.")
parser.add_argument("--expected-api-mode", help="Require the exact configured LLM API mode.")
parser.add_argument("--expected-response-format", help="Require the exact configured structured-output mode.")
parser.add_argument("--expected-temperature", type=float, help="Require this temperature in Author and Visual director requests.")
parser.add_argument("--expected-vfx-temperature", type=float, help="Require the configured VFX director temperature without changing it.")
parser.add_argument(
    "--expected-repair-temperature",
    type=float,
    help="Require this temperature in Gameplay, Visual, and VFX Repair requests; defaults to --expected-temperature.",
)
parser.add_argument("--expected-max-tokens", type=int, help="Require this answer-token budget in Author and Gameplay Repair requests.")
parser.add_argument(
    "--expected-visual-max-tokens", type=int,
    help="Require this answer-token budget in Visual Director/Repair requests; defaults to --expected-max-tokens.",
)
parser.add_argument(
    "--expected-vfx-max-tokens", type=int,
    help="Require this answer-token budget in VFX Director/Repair requests; defaults to --expected-max-tokens.",
)
parser.add_argument("--expected-reasoning-effort", help="Require this provider reasoning_effort in every LLM request.")
parser.add_argument("--expected-head", help="Require this clean Git HEAD before starting the campaign.")
parser.add_argument("--require-no-fallback", action="store_true", help="Reject fallback and enabled pool routes.")
parser.add_argument(
    "--require-zero-transport-retries",
    action="store_true",
    help="Fail if any successful logical LLM call needed a hidden low-level HTTP retry.",
)
parser.add_argument("--min-first-author", type=int, default=10, help="Required successes with one initial Author call and no repair.")
parser.add_argument("--parallel-crafts", type=int, default=3, help="Concurrent craft workers; Live20 defaults to exactly three.")
parser.add_argument("--preflight-only", action="store_true", help="Validate frozen config, v5 imports, cases and image boundary without network calls.")
args = parser.parse_args()
if args.transport_retries < 0 or args.transport_retries > 100:
    raise SystemExit("--transport-retries must be within 0..100")
if args.transport_retry_delay_seconds < 60 or args.transport_retry_delay_seconds > 3600:
    raise SystemExit("--transport-retry-delay-seconds must be within 60..3600")
if args.parallel_crafts < 1 or args.parallel_crafts > 8:
    raise SystemExit("--parallel-crafts must be within 1..8")

ROOT = discover_project(args.project)
LOCAL = ROOT / 'LocalGenerator'
OUT = Path(args.output or os.environ.get('INFINI_LIVE_OUT') or new_run_dir('live-no-image'))
OUT.mkdir(parents=True, exist_ok=True)

# Load the user's actual LLM profile without printing secrets. The test overrides only
# isolation/trace settings; image semantics stay on the configured sdcpp backend.
load_config_env(ROOT)

configured_provider = str(os.environ.get('INFINI_LLM_PROVIDER') or '').strip()
configured_model = str(os.environ.get('INFINI_OPENAI_COMPAT_MODEL') or '').strip()
configured_base_url = str(os.environ.get('INFINI_OPENAI_COMPAT_BASE_URL') or '').strip().rstrip('/') + '/'
configured_api_mode = str(os.environ.get('INFINI_LLM_API_MODE') or 'auto').strip().lower()
configured_response_format = str(os.environ.get('INFINI_LLM_RESPONSE_FORMAT') or 'auto').strip().lower()
expected_provider = str(args.expected_provider or '').strip()
expected_model = str(args.expected_model or '').strip()
expected_base_url = str(args.expected_base_url or '').strip().rstrip('/') + '/' if args.expected_base_url else ''
if expected_provider and configured_provider != expected_provider:
    raise SystemExit(f"configured provider {configured_provider!r} != expected {expected_provider!r}")
if expected_model and configured_model != expected_model:
    raise SystemExit(f"configured model {configured_model!r} != expected {expected_model!r}")
if expected_base_url and configured_base_url != expected_base_url:
    raise SystemExit(f"configured base URL {configured_base_url!r} != expected {expected_base_url!r}")
if args.expected_api_mode and configured_api_mode != str(args.expected_api_mode).strip().lower():
    raise SystemExit(f"configured API mode {configured_api_mode!r} != expected {args.expected_api_mode!r}")
if args.expected_response_format and configured_response_format != str(args.expected_response_format).strip().lower():
    raise SystemExit(
        f"configured response format {configured_response_format!r} != expected {args.expected_response_format!r}"
    )

fallback_state = {
    'provider': str(os.environ.get('INFINI_LLM_FALLBACK_PROVIDER') or '').strip(),
    'model': str(os.environ.get('INFINI_LLM_FALLBACK_MODEL') or '').strip(),
    'legacyRepairModel': str(os.environ.get('INFINI_LLM_REAUTHOR_MODEL') or '').strip(),
    'enabledPools': [
        slot for slot in (2, 3, 4)
        if str(os.environ.get(f'INFINI_LLM_POOL_{slot}_ENABLED') or '0').strip() == '1'
    ],
}
if args.require_no_fallback and any((
    fallback_state['provider'], fallback_state['model'],
    fallback_state['legacyRepairModel'], fallback_state['enabledPools'],
)):
    raise SystemExit(f"fallback/model hopping is configured: {fallback_state}")

git_head = subprocess.check_output(
    ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True,
).strip()
git_status = subprocess.check_output(
    ['git', '-C', str(ROOT), 'status', '--porcelain'], text=True,
).strip()
if args.expected_head:
    if git_head != str(args.expected_head).strip():
        raise SystemExit(f"project HEAD {git_head} != expected {args.expected_head}")
    if git_status:
        raise SystemExit("--expected-head requires a clean project worktree")

os.environ['INFINI_CACHE_DIR'] = str(OUT / 'cache')
os.environ['INFINI_TRACE_PROMPTS'] = '1'
os.environ['INFINI_TRACE_MAX_PROMPT_CHARS'] = '200000'
os.environ['INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK'] = '0'
os.environ['INFINI_VISUAL_REQUIRE_ITEM_SPRITE'] = '0'
# Pacing is owned by this harness. Do not permit lower-level transport retries
# to fire immediately, or their attempts would escape the one-minute ledger.
if args.transport_retries > 0 or args.require_zero_transport_retries:
    os.environ['INFINI_LLM_FALLBACK_NETWORK_FAILS'] = '1'
sys.path.insert(0, str(LOCAL))

SUPPORT_PATH = Path(__file__).with_name("live20_support_v5.py")
from live20_support_v5 import (  # noqa: E402
    NON_AUTHOR,
    FROZEN_LLM_STAGES,
    expected_stage_max_tokens,
    expected_stage_temperature,
    response_format_type,
    GlobalStageAccounting,
    author_stage,
    case_accounting_scope,
    current_case_accounting,
    is_first_author_success,
    should_retry_case_failure,
    case_transport_retry_report,
    pace_case_transport_retry,
    transport_retry_summary,
    valid_author_call_budget,
    run_parallel_crafts,
    select_case_routes,
    write_no_image_fixture_png,
    hydrate_no_image_fixture_assets,
)
from infini_local.pipelines import llm_transport  # noqa: E402

if (args.transport_retries > 0 or args.require_zero_transport_retries) and int(llm_transport.LLM_FALLBACK_NETWORK_FAILS) != 1:
    raise SystemExit(
        "paced case retries require one physical HTTP attempt per logical call "
        f"(loaded {llm_transport.LLM_FALLBACK_NETWORK_FAILS})"
    )

LOGICAL = OUT / 'logical_llm.ndjson'
HTTP = OUT / 'http_llm.ndjson'
IMAGES = OUT / 'image_boundary.ndjson'
RESULTS = OUT / 'results.ndjson'
HARNESS_EVENTS = OUT / 'harness_events.ndjson'
for path in (LOGICAL, HTTP, IMAGES, RESULTS, HARNESS_EVENTS):
    path.write_text('', encoding='utf-8')
NO_IMAGE_FIXTURE = write_no_image_fixture_png(OUT / 'qa-no-image-fixture.png')

trace_write_lock = threading.Lock()
progress_write_lock = threading.Lock()


def append(path: Path, row: dict[str, Any]) -> None:
    with trace_write_lock:
        with path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str, separators=(',', ':')) + '\n')


def progress(message: str) -> None:
    with progress_write_lock:
        print(message, flush=True)


def wall_time_fields() -> dict[str, Any]:
    now = time.time()
    return {
        'wallTimeUnix': now,
        'wallTimeUtc': datetime.fromtimestamp(now, timezone.utc).isoformat(),
    }


def case_trace_fields() -> dict[str, Any]:
    state = current_case_accounting()
    if state is None:
        return {}
    return {'case': state.case_id, 'caseIndex': state.case_index}


original_http_json = llm_transport.http_json
original_llm_chat_json = llm_transport.llm_chat_json
global_accounting = GlobalStageAccounting()


def lease_snapshot() -> dict[str, Any] | None:
    lease = llm_transport.current_llm_item_lease()
    return lease.snapshot() if lease is not None else None

def captured_http_json(url: str, payload: dict[str, Any], timeout: int = 10, headers: dict[str, str] | None = None):
    concurrency_start = global_accounting.begin_http()
    sequence = int(concurrency_start['sequence'])
    started = time.time()
    append(HTTP, {
        'sequence': sequence,
        'phase': 'request',
        'url': url,
        'timeout': timeout,
        'payload': copy.deepcopy(payload),
        'authorizationPresent': bool((headers or {}).get('Authorization')),
        **{key: value for key, value in concurrency_start.items() if key != 'sequence'},
        **wall_time_fields(),
        **case_trace_fields(),
    })

    ended = False
    try:
        request_model = str(payload.get('model') or '').strip()
        if expected_model and request_model != expected_model:
            raise RuntimeError(f"request model {request_model!r} != frozen campaign model {expected_model!r}")
        if expected_base_url and not str(url).startswith(expected_base_url):
            raise RuntimeError(f"request URL {url!r} escaped frozen campaign endpoint {expected_base_url!r}")
        result = original_http_json(url, payload, timeout=timeout, headers=headers)
        concurrency_end = global_accounting.end_http()
        ended = True
        append(HTTP, {
            'sequence': sequence,
            'phase': 'response',
            'url': url,
            'ms': int((time.time() - started) * 1000),
            'response': result,
            **concurrency_end,
            **wall_time_fields(),
            **case_trace_fields(),
        })
        return result
    except Exception as exc:
        concurrency_end = global_accounting.snapshot() if ended else global_accounting.end_http()
        append(HTTP, {
            'sequence': sequence,
            'phase': 'error',
            'url': url,
            'ms': int((time.time() - started) * 1000),
            'error': repr(exc),
            **{key: concurrency_end[key] for key in (
                'activeCrafts', 'activeLogical', 'activeHttp',
                'peakActiveCrafts', 'peakActiveLogical', 'peakActiveHttp',
            )},
            **wall_time_fields(),
            **case_trace_fields(),
        })
        raise

llm_transport.http_json = captured_http_json


def assert_frozen_logical_settings(payload: dict[str, Any], *, stage: str) -> None:
    if expected_model and str(payload.get('model') or '').strip() != expected_model:
        raise RuntimeError(f"logical request model escaped frozen campaign model {expected_model!r}")
    if stage == NON_AUTHOR or stage not in FROZEN_LLM_STAGES:
        raise RuntimeError(f"unclassified LLM stage escaped frozen campaign settings: {stage!r}")
    frozen_temperature = expected_stage_temperature(
        stage,
        director_temperature=args.expected_temperature,
        repair_temperature=args.expected_repair_temperature,
        vfx_director_temperature=args.expected_vfx_temperature,
    )
    if frozen_temperature is not None:
        request_temperature = float(cast(str | int | float, payload.get('temperature')))
        if request_temperature != frozen_temperature:
            raise RuntimeError(
                f"logical {stage} request temperature {request_temperature!r} "
                f"!= frozen stage temperature {frozen_temperature!r}"
            )
    frozen_max_tokens = expected_stage_max_tokens(
        stage,
        author_tokens=args.expected_max_tokens,
        visual_tokens=args.expected_visual_max_tokens,
        vfx_tokens=args.expected_vfx_max_tokens,
    )
    if frozen_max_tokens is not None:
        request_max_tokens = payload.get('max_tokens', payload.get('max_completion_tokens'))
        if request_max_tokens is None or int(request_max_tokens) != frozen_max_tokens:
            raise RuntimeError(
                f"logical {stage} request max tokens {request_max_tokens!r} "
                f"!= frozen stage budget {frozen_max_tokens!r}"
            )
    if args.expected_reasoning_effort:
        request_reasoning_effort = str(payload.get('reasoning_effort') or '').strip()
        if request_reasoning_effort != args.expected_reasoning_effort:
            raise RuntimeError(
                f"logical request reasoning effort {request_reasoning_effort!r} != frozen campaign effort {args.expected_reasoning_effort!r}"
            )
    frozen_response_format = str(args.expected_response_format or "").strip().lower()
    if frozen_response_format:
        request_response_format = response_format_type(payload).lower()
        if request_response_format != frozen_response_format:
            raise RuntimeError(
                f"logical request response format {request_response_format!r} "
                f"!= frozen campaign response format {frozen_response_format!r}"
            )


def captured_llm_chat_json(payload: dict[str, Any], timeout: int = 10):
    stage = author_stage(payload)
    global_event = global_accounting.begin_logical(stage)
    sequence = int(global_event['sequence'] or 0)
    case_state = current_case_accounting()
    case_sequence = case_state.begin_logical(stage) if case_state is not None else 0
    lease_before = lease_snapshot()
    started = time.time()
    ended = False
    try:
        append(LOGICAL, {
            'sequence': sequence,
            'caseLogicalSequence': case_sequence or None,
            'authorSequence': global_event['authorSequence'],
            'initialAuthorSequence': global_event['initialAuthorSequence'],
            'scopedRepairSequence': global_event['scopedRepairSequence'],
            'llmStage': stage,
            'phase': 'request',
            'lease': lease_before,
            'timeout': timeout,
            'payload': copy.deepcopy(payload),
            **{key: value for key, value in global_event.items() if key.startswith('active') or key.startswith('peak')},
            **wall_time_fields(),
            **case_trace_fields(),
        })
        assert_frozen_logical_settings(payload, stage=stage)
        result = original_llm_chat_json(payload, timeout=timeout)
        concurrency_end = global_accounting.end_logical()
        ended = True
        append(LOGICAL, {
            'sequence': sequence,
            'caseLogicalSequence': case_sequence or None,
            'llmStage': stage,
            'phase': 'response',
            'lease': lease_snapshot(),
            'ms': int((time.time() - started) * 1000),
            'response': result,
            **concurrency_end,
            **wall_time_fields(),
            **case_trace_fields(),
        })
        return result
    except Exception as exc:
        concurrency_end = global_accounting.snapshot() if ended else global_accounting.end_logical()
        transport_error = bool(llm_transport._is_transport_error(exc))
        if case_state is not None:
            case_state.mark_logical_error(case_sequence, transport=transport_error)
        append(LOGICAL, {
            'sequence': sequence,
            'caseLogicalSequence': case_sequence or None,
            'llmStage': stage,
            'phase': 'error',
            'lease': lease_snapshot(),
            'ms': int((time.time() - started) * 1000),
            'transportError': transport_error,
            'error': repr(exc),
            **{key: concurrency_end[key] for key in (
                'activeCrafts', 'activeLogical', 'activeHttp',
                'peakActiveCrafts', 'peakActiveLogical', 'peakActiveHttp',
            )},
            **wall_time_fields(),
            **case_trace_fields(),
        })
        raise

llm_transport.llm_chat_json = captured_llm_chat_json

# Import the pipeline only after installing the logical transport wrapper so every
# stage receives the same wrapped function object.
from infini_local.pipelines import combine_pipeline as combine  # noqa: E402
from infini_local.pipelines import visual_sprite_generation as sprites  # noqa: E402
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan  # noqa: E402
from infini_local.pipelines.visual_prompt_contracts import asset_negative_prompt, normalize_asset_prompt  # noqa: E402

# No recipe cache/world mutation during this live diagnostic.
def no_cache_get(*_args: Any, **_kwargs: Any) -> None:
    return None

def no_cache_put(*_args: Any, **_kwargs: Any) -> None:
    return None

def attach_asset_sync_meta(data: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    return data

def attach_recipe_health(data: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    return data

combine.cache_get = no_cache_get
combine.cache_put = no_cache_put
combine.asset_sync_service.attach_asset_sync_meta = attach_asset_sync_meta
combine.world_storage.attach_recipe_health = attach_recipe_health

# Hard proof that no configured image generator can be reached.
def forbidden_backend(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError('IMAGE BACKEND WAS CALLED DURING NO-IMAGE LIVE TEST')

sprites._generate_backend_variants = forbidden_backend
sprites.generate_visual_asset = forbidden_backend

def capture_image_boundary(data: dict[str, Any]) -> dict[str, Any]:
    probe = copy.deepcopy(data)
    visual = probe.setdefault('visual', {})
    runtime = cast(dict[str, Any], probe.get('runtimeProgram')) if isinstance(probe.get('runtimeProgram'), dict) else {}
    primary_entity_id = str(runtime.get('primaryEntityId') or '')
    primary_entity = next((
        row for row in runtime.get('entities') or []
        if isinstance(row, dict) and str(row.get('id') or '') == primary_entity_id
    ), {})
    kit = cast(dict[str, Any], probe.get('visualKit')) if isinstance(probe.get('visualKit'), dict) else {}
    director_negative = str(kit.get('negativePrompt') or '').strip()

    item_canvas = int(visual.get('preferredCanvasSize') or 32)
    item_prompt = normalize_asset_prompt(probe, 'item', str(visual.get('imagePrompt') or ''), item_canvas)
    item_negative = str(visual.get('negativePrompt') or asset_negative_prompt('item'))
    visual['imagePrompt'] = item_prompt
    visual['finalItemPrompt'] = item_prompt[:1800]
    plan = build_visual_asset_plan(probe)

    backend_rows: list[dict[str, Any]] = []
    for slot in plan:
        role = str(slot.get('role') or '')
        canvas = int(slot.get('canvas') or 32)
        status = str(slot.get('status') or '')
        mode = str(slot.get('assetMode') or '')
        should_call = role == 'item' or (mode == 'baked_sprite' and not status.startswith('skipped_'))
        raw_prompt = str(slot.get('prompt') or '')
        final_prompt = item_prompt if role == 'item' else normalize_asset_prompt(probe, role, raw_prompt, canvas)
        negative = item_negative if role == 'item' else (director_negative or asset_negative_prompt(role))
        backend_rows.append({
            'role': role,
            'assetId': slot.get('assetId'),
            'canvas': canvas,
            'assetMode': mode,
            'required': bool(slot.get('required')),
            'statusBeforeBackend': status,
            'shouldCallBackend': should_call,
            'rawPrompt': raw_prompt,
            'finalPrompt': final_prompt,
            'negativePrompt': negative,
            'checks': {
                'nonempty': bool(final_prompt.strip()),
                'withinBackendBoundary': len(final_prompt) <= 1800,
                'historyAbsent': '_llmHistory' not in final_prompt,
                'promptChars': len(final_prompt),
            },
        })

    append(IMAGES, {
        **case_trace_fields(),
        'qaFixturePath': str(NO_IMAGE_FIXTURE),
        'itemId': probe.get('id'),
        'name': probe.get('name'),
        'category': probe.get('category'),
        'primaryEntityId': primary_entity_id,
        'primaryEntityKind': primary_entity.get('kind'),
        'parents': [probe.get('parentA'), probe.get('parentB')],
        'visualKit': kit,
        'visual': visual,
        'finalContract': copy.deepcopy(probe),
        'assetPlan': plan,
        'backendCallsThatWouldOccur': backend_rows,
    })

    # Preserve prompt-only evidence, then hydrate final-delivery paths with one
    # deterministic QA fixture. The configured backend remains hard-blocked.
    data_visual = data.setdefault('visual', {})
    data_visual['imagePrompt'] = item_prompt
    data_visual['finalItemPrompt'] = item_prompt[:1800]
    data.setdefault('debug', {})['visualAssetPlan'] = json.dumps(plan, ensure_ascii=False)
    return hydrate_no_image_fixture_assets(data, NO_IMAGE_FIXTURE)

combine.maybe_generate_visual_assets = capture_image_boundary
def identity_data(data: dict[str, Any]) -> dict[str, Any]:
    return data

combine.assert_visual_delivery_ready = identity_data


def parent(name: str, **fields: Any) -> dict[str, Any]:
    base = {
        'name': name,
        'internalName': name.replace(' ', ''),
        'fullName': f'Terraria/{name.replace(" ", "")}',
        'type': fields.pop('type', 1),
        'netId': fields.pop('netId', 1),
        'stack': 1,
        'maxStack': fields.pop('maxStack', 1),
        'rarity': fields.pop('rarity', 1),
        'value': fields.pop('value', 1000),
        'material': fields.pop('material', True),
        'tooltip': fields.pop('tooltip', ''),
        'tags': fields.pop('tags', []),
    }
    base.update(fields)
    return base

ROUTES: list[tuple[str, str, str]] = [
    ("woodwork_blade", "WoodenSword", "WorkBench"),
    ("astral_mirror", "MagicMirror", "FallenStar"),
    ("bee_boomstick", "Boomstick", "BeeWax"),
    ("swift_boots", "HermesBoots", "Aglet"),
    ("ropebound_spear", "Spear", "Rope"),
    ("infernal_boomerang", "EnchantedBoomerang", "HellstoneBar"),
    ("meteor_spacegun", "SpaceGun", "MeteoriteBar"),
    ("astral_minishark", "Minishark", "FallenStar"),
    ("chained_ball", "BallOHurt", "Chain"),
    ("corrupt_yoyo", "CorruptYoyo", "DemoniteBar"),
    ("jungle_whip", "ThornWhip", "JungleSpores"),
    ("lens_finch_staff", "BabyBirdStaff", "Lens"),
    ("spider_sentry", "QueenSpiderStaff", "SpiderFang"),
    ("gel_grenade", "Grenade", "Gel"),
    ("jester_bow", "WoodenBow", "JestersArrow"),
    ("obsidian_pickaxe", "MoltenPickaxe", "Obsidian"),
    ("vital_regen_band", "BandofRegeneration", "LifeCrystal"),
    ("torch_mining_helmet", "MiningHelmet", "Torch"),
    ("glowing_healing_potion", "HealingPotion", "GlowingMushroom"),
    ("silt_extractinator", "Extractinator", "SiltBlock"),
    ("gel_slime_staff", "SlimeStaff", "Gel"),
    ("torch_iron_sword", "IronBroadsword", "Torch"),
    ("feather_cloud_bottle", "CloudinaBottle", "Feather"),
    ("astral_star_cannon", "StarCannon", "FallenStar"),
    ("wax_bee_gun", "BeeGun", "BeeWax"),
    ("infernal_flamarang", "Flamarang", "HellstoneBar"),
]
FIXED_ACCEPTANCE_CASE_IDS = tuple(case_id for case_id, _, _ in ROUTES[:20])
runtime_dump = (args.runtime_dump or TOOLBOX / "fixtures/items.jsonl").expanduser().resolve()
if not runtime_dump.is_file():
    raise SystemExit(f"parent runtime dump is missing: {runtime_dump}")
items: dict[str, dict[str, Any]] = {}
with runtime_dump.open(encoding="utf-8-sig") as fh:
    for line in fh:
        if not line.strip():
            continue
        row = json.loads(line)
        internal = str(row.get("internalName") or "")
        if internal:
            items[internal] = row

active_routes = ROUTES
cases_file_path = ""
cases_file_sha256 = ""
if args.cases_file:
    source_path = args.cases_file.expanduser().resolve()
    raw_payload = json.loads(source_path.read_text(encoding="utf-8"))
    raw_cases = raw_payload.get("cases") if isinstance(raw_payload, dict) else raw_payload
    if not isinstance(raw_cases, list):
        raise SystemExit("--cases-file must contain a list or an object with a cases list")
    parsed_routes: list[tuple[str, str, str]] = []
    seen_case_ids: set[str] = set()
    for index, row in enumerate(raw_cases):
        if not isinstance(row, dict):
            raise SystemExit(f"--cases-file row {index} must be an object")
        case_id = str(row.get("case") or "").strip()
        parent_a = str(row.get("itemA") or "").strip()
        parent_b = str(row.get("itemB") or "").strip()
        if (
            not case_id
            or len(case_id) > 64
            or not case_id.replace("_", "").isalnum()
            or case_id.lower() != case_id
        ):
            raise SystemExit(f"--cases-file row {index} has invalid case ID {case_id!r}")
        if not parent_a or not parent_b:
            raise SystemExit(f"--cases-file row {index} requires itemA and itemB")
        if case_id in seen_case_ids:
            raise SystemExit(f"--cases-file repeats case ID {case_id!r}")
        seen_case_ids.add(case_id)
        parsed_routes.append((case_id, parent_a, parent_b))
    if not parsed_routes:
        raise SystemExit("--cases-file has no cases")
    active_routes = parsed_routes
    cases_file_path = str(source_path)
    cases_file_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()

case_filter_text = args.cases if args.cases is not None else os.environ.get('INFINI_LIVE_CASES', '')
case_filter = {value.strip() for value in case_filter_text.split(',') if value.strip()}
if not case_filter and not args.cases_file:
    case_filter = set(FIXED_ACCEPTANCE_CASE_IDS)
try:
    selected_routes = select_case_routes(active_routes, case_filter)
except ValueError as error:
    raise SystemExit(str(error)) from error
missing_items = sorted({
    name for _, a_name, b_name in selected_routes
    for name in (a_name, b_name) if name not in items
})
if missing_items:
    raise SystemExit(f"runtime dump is missing: {', '.join(missing_items)}")
selected_cases = [
    (case_id, copy.deepcopy(items[parent_a]), copy.deepcopy(items[parent_b]))
    for case_id, parent_a, parent_b in selected_routes
]
if not selected_cases:
    raise SystemExit("no live cases selected")
if args.expected_case_count is not None and len(selected_cases) != args.expected_case_count:
    raise SystemExit(f"selected {len(selected_cases)} cases, expected {args.expected_case_count}")
if args.min_first_author < 0 or args.min_first_author > len(selected_cases):
    raise SystemExit(f"--min-first-author must be within 0..{len(selected_cases)}")

campaign_identity = {
    'schema': 'infini.live-campaign-identity.v1',
    'project': str(ROOT),
    'gitHead': git_head,
    'gitClean': not bool(git_status),
    'runnerSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'stageAccountingSha256': hashlib.sha256(SUPPORT_PATH.read_bytes()).hexdigest(),
    'runtimeDumpSha256': hashlib.sha256(runtime_dump.read_bytes()).hexdigest(),
    'provider': configured_provider,
    'model': configured_model,
    'baseUrl': configured_base_url,
    'apiMode': configured_api_mode,
    'responseFormat': configured_response_format,
    'expectedProvider': expected_provider,
    'expectedModel': expected_model,
    'expectedBaseUrl': expected_base_url,
    'expectedApiMode': args.expected_api_mode,
    'expectedResponseFormat': args.expected_response_format,
    'expectedTemperature': args.expected_temperature,
    'expectedVfxTemperature': args.expected_vfx_temperature,
    'expectedRepairTemperature': (
        args.expected_repair_temperature
        if args.expected_repair_temperature is not None
        else args.expected_temperature
    ),
    'expectedMaxTokens': args.expected_max_tokens,
    'expectedVisualMaxTokens': (
        args.expected_visual_max_tokens
        if args.expected_visual_max_tokens is not None
        else args.expected_max_tokens
    ),
    'expectedVfxMaxTokens': (
        args.expected_vfx_max_tokens
        if args.expected_vfx_max_tokens is not None
        else args.expected_max_tokens
    ),
    'expectedReasoningEffort': args.expected_reasoning_effort,
    'samplingFreezeStages': list(FROZEN_LLM_STAGES),
    'fallbackState': fallback_state,
    'cases': [case[0] for case in selected_cases],
    'casesFile': cases_file_path,
    'casesFileSha256': cases_file_sha256,
    'expectedCaseCount': args.expected_case_count,
    'minFirstAuthor': args.min_first_author,
    'transportRetries': args.transport_retries,
    'transportRetryDelaySeconds': args.transport_retry_delay_seconds,
    'transportRetryScope': 'case_only_after_confirmed_logical_transport_error',
    'requireZeroTransportRetries': bool(args.require_zero_transport_retries),
    'networkAttemptBudget': int(llm_transport.LLM_FALLBACK_NETWORK_FAILS),
    'parallelCrafts': args.parallel_crafts,
    'imagesDisabled': True,
    'preflightOnly': bool(args.preflight_only),
}
(OUT / 'campaign_manifest.json').write_text(
    json.dumps(campaign_identity, ensure_ascii=False, indent=2), encoding='utf-8',
)
if args.preflight_only:
    print(json.dumps({"ok": True, "preflightOnly": True, "campaignIdentity": campaign_identity}, ensure_ascii=False), flush=True)
    raise SystemExit(0)

def _run_case(job: tuple[int, tuple[str, dict[str, Any], dict[str, Any]]]) -> tuple[dict[str, Any], int]:
    index, (case_id, item_a, item_b) = job
    with case_accounting_scope(case_id, index) as case_state:
        payload = {
            'itemA': item_a,
            'itemB': item_b,
            'worldId': 910000 + index,
            'worldName': f'GLM20_NoImage_{case_id}',
        }
        for transport_attempt in range(1, args.transport_retries + 2):
            started = time.time()
            before = case_state.snapshot()
            append(HARNESS_EVENTS, {
                'event': 'CASE_ATTEMPT_START', 'case': case_id, 'caseIndex': index,
                'attempt': transport_attempt, **wall_time_fields(),
            })
            try:
                result = combine.combine(payload)
            except Exception as exc:
                metrics = case_state.delta_since(before)
                initial_author_calls = metrics['initialAuthorCalls']
                scoped_repair_calls = metrics['scopedRepairCalls']
                retryable_transport = should_retry_case_failure(
                    had_logical_error=(
                        metrics['logicalRequests'] > 0
                        and case_state.last_logical_error_sequence == case_state.last_logical_sequence
                    ),
                    low_level_transport_error=case_state.last_logical_error_transport,
                )
                append(HARNESS_EVENTS, {
                    'event': 'CASE_ATTEMPT_END', 'case': case_id, 'caseIndex': index,
                    'attempt': transport_attempt,
                    'outcome': 'transport_error' if retryable_transport else 'nontransport_error',
                    'caseLogicalSequence': case_state.last_logical_sequence,
                    'logicalRequests': metrics['logicalRequests'], **wall_time_fields(),
                })
                if retryable_transport and transport_attempt <= args.transport_retries:
                    case_state.case_transport_retries += 1
                    append(HARNESS_EVENTS, {
                        'event': 'CASE_RETRY_SCHEDULED', 'case': case_id, 'caseIndex': index,
                        'attempt': transport_attempt,
                        'caseLogicalSequence': case_state.last_logical_sequence,
                        'waitSeconds': args.transport_retry_delay_seconds, **wall_time_fields(),
                    })
                    progress(
                        f'[{index}/{len(selected_cases)}] RETRY transport {case_id} '
                        f'attempt={transport_attempt} after {args.transport_retry_delay_seconds}s: {exc!r}'
                    )
                    elapsed = pace_case_transport_retry(args.transport_retry_delay_seconds)
                    append(HARNESS_EVENTS, {
                        'event': 'CASE_RETRY_WAIT_COMPLETE', 'case': case_id, 'caseIndex': index,
                        'attempt': transport_attempt,
                        'caseLogicalSequence': case_state.last_logical_sequence,
                        'elapsedSeconds': elapsed, **wall_time_fields(),
                    })
                    continue
                row = {
                    'case': case_id,
                    'caseIndex': index,
                    'caseAttempts': transport_attempt,
                    'caseTransportRetries': case_state.case_transport_retries,
                    'ok': False,
                    'ms': int((time.time() - started) * 1000),
                    'logicalRequests': metrics['logicalRequests'],
                    'authorAttempts': initial_author_calls + scoped_repair_calls,
                    'initialAuthorCalls': initial_author_calls,
                    'scopedRepairCalls': scoped_repair_calls,
                    'authorCallBudgetValid': valid_author_call_budget(
                        initial_calls=initial_author_calls,
                        repair_calls=scoped_repair_calls,
                    ),
                    'firstAuthorSuccess': False,
                    'repairFree': False,
                    'error': repr(exc),
                    'traceback': traceback.format_exc(),
                }
                progress(f'[{index}/{len(selected_cases)}] FAIL {case_id}: {exc!r}')
                return row, case_state.case_transport_retries

            metrics = case_state.delta_since(before)
            logical_requests = metrics['logicalRequests']
            initial_author_calls = metrics['initialAuthorCalls']
            scoped_repair_calls = metrics['scopedRepairCalls']
            author_attempts = initial_author_calls + scoped_repair_calls
            budget_valid = valid_author_call_budget(
                initial_calls=initial_author_calls,
                repair_calls=scoped_repair_calls,
            )
            first_author_success = is_first_author_success(
                initial_calls=initial_author_calls,
                repair_calls=scoped_repair_calls,
            )
            if not budget_valid:
                append(HARNESS_EVENTS, {
                    'event': 'CASE_ATTEMPT_END', 'case': case_id, 'caseIndex': index,
                    'attempt': transport_attempt, 'outcome': 'author_budget_violation',
                    'caseLogicalSequence': case_state.last_logical_sequence,
                    'logicalRequests': logical_requests, **wall_time_fields(),
                })
                row = {
                    'case': case_id,
                    'caseIndex': index,
                    'caseAttempts': transport_attempt,
                    'caseTransportRetries': case_state.case_transport_retries,
                    'ok': False,
                    'ms': int((time.time() - started) * 1000),
                    'logicalRequests': logical_requests,
                    'authorAttempts': author_attempts,
                    'initialAuthorCalls': initial_author_calls,
                    'scopedRepairCalls': scoped_repair_calls,
                    'authorCallBudgetValid': False,
                    'firstAuthorSuccess': False,
                    'repairFree': False,
                    'error': 'author_call_budget_violation',
                }
                progress(
                    f'[{index}/{len(selected_cases)}] FAIL {case_id}: '
                    f'initialAuthorCalls={initial_author_calls} scopedRepairCalls={scoped_repair_calls}'
                )
                return row, case_state.case_transport_retries

            append(HARNESS_EVENTS, {
                'event': 'CASE_ATTEMPT_END', 'case': case_id, 'caseIndex': index,
                'attempt': transport_attempt, 'outcome': 'success',
                'caseLogicalSequence': case_state.last_logical_sequence,
                'logicalRequests': logical_requests, **wall_time_fields(),
            })
            row = {
                'case': case_id,
                'caseIndex': index,
                'caseAttempts': transport_attempt,
                'caseTransportRetries': case_state.case_transport_retries,
                'ok': True,
                'ms': int((time.time() - started) * 1000),
                'logicalRequests': logical_requests,
                'authorAttempts': author_attempts,
                'initialAuthorCalls': initial_author_calls,
                'scopedRepairCalls': scoped_repair_calls,
                'authorCallBudgetValid': True,
                'firstAuthorSuccess': first_author_success,
                'repairFree': first_author_success,
                'id': result.get('id'),
                'name': result.get('name'),
                'category': result.get('category'),
                'primaryEntityId': (result.get('runtimeProgram') or {}).get('primaryEntityId'),
                'primaryEntityKind': next((
                    entity.get('kind')
                    for entity in (result.get('runtimeProgram') or {}).get('entities') or []
                    if isinstance(entity, dict)
                    and entity.get('id') == (result.get('runtimeProgram') or {}).get('primaryEntityId')
                ), None),
                'visualPrompt': (result.get('visual') or {}).get('imagePrompt'),
                'spriteStatus': (result.get('visual') or {}).get('spriteStatus'),
                'debug': result.get('debug'),
            }
            progress(
                f'[{index}/{len(selected_cases)}] PASS {case_id}: {result.get("name")} | '
                f'primary={(result.get("runtimeProgram") or {}).get("primaryEntityId")} | '
                f'initialAuthorCalls={initial_author_calls} scopedRepairCalls={scoped_repair_calls} '
                f'allLlmStages={logical_requests} firstAuthorSuccess={first_author_success} | '
                f'{int((time.time()-started)*1000)} ms'
            )
            return row, case_state.case_transport_retries

    raise RuntimeError(f'case worker exhausted without a result: {case_id}')


def run_case(job: tuple[int, tuple[str, dict[str, Any], dict[str, Any]]]) -> tuple[dict[str, Any], int]:
    index, (case_id, _item_a, _item_b) = job
    started = time.time()
    concurrency_start = global_accounting.begin_craft()
    try:
        append(HARNESS_EVENTS, {
            'event': 'CRAFT_START', 'case': case_id, 'caseIndex': index,
            **concurrency_start, **wall_time_fields(),
        })
        return _run_case(job)
    finally:
        concurrency_end = global_accounting.end_craft()
        append(HARNESS_EVENTS, {
            'event': 'CRAFT_END', 'case': case_id, 'caseIndex': index,
            'ms': int((time.time() - started) * 1000),
            **concurrency_end, **wall_time_fields(),
        })


transport_failures = 0
case_jobs = list(enumerate(selected_cases, 1))

def record_completed_case(result: tuple[dict[str, Any], int]) -> None:
    append(RESULTS, result[0])  # Persist before the next/earlier in-flight case finishes.

for _result_row, ignored_transport_failures in run_parallel_crafts(
    run_case,
    case_jobs,
    parallel_crafts=args.parallel_crafts,
    on_result=record_completed_case,
):
    transport_failures += ignored_transport_failures

global_counts = global_accounting.snapshot()

summary: dict[str, Any] = {
    'schema': 'infini.live-no-image-summary.v3',
    'project': str(ROOT),
    'campaignIdentity': campaign_identity,
    'cases': len(selected_cases),
    'logicalRequests': global_counts['logicalRequests'],
    'authorAttempts': global_counts['authorAttempts'],
    'initialAuthorCalls': global_counts['initialAuthorCalls'],
    'scopedRepairCalls': global_counts['scopedRepairCalls'],
    'httpRequests': global_counts['httpRequests'],
    'concurrency': {
        key: global_counts[key]
        for key in (
            'activeCrafts', 'activeLogical', 'activeHttp',
            'peakActiveCrafts', 'peakActiveLogical', 'peakActiveHttp',
        )
    },
    'resultRows': sum(1 for _ in RESULTS.open(encoding='utf-8')),
    'imageBoundaryRows': sum(1 for _ in IMAGES.open(encoding='utf-8')),
    'artifacts': {
        'logical': str(LOGICAL),
        'http': str(HTTP),
        'imageBoundary': str(IMAGES),
        'results': str(RESULTS),
        'harnessEvents': str(HARNESS_EVENTS),
        'promptTrace': str(OUT / 'cache' / 'prompt_trace.ndjson'),
        'events': str(OUT / 'cache' / 'events.ndjson'),
    },
}
result_rows = [json.loads(line) for line in RESULTS.read_text(encoding='utf-8').splitlines() if line.strip()]
logical_rows = [json.loads(line) for line in LOGICAL.read_text(encoding='utf-8').splitlines() if line.strip()]
harness_rows = [json.loads(line) for line in HARNESS_EVENTS.read_text(encoding='utf-8').splitlines() if line.strip()]
image_rows = [json.loads(line) for line in IMAGES.read_text(encoding='utf-8').splitlines() if line.strip()]
successful_case_ids = [str(row.get('case') or '') for row in result_rows if row.get('ok')]
image_case_counts = {
    case_id: sum(1 for row in image_rows if str(row.get('case') or '') == case_id)
    for case_id in set(successful_case_ids + [str(row.get('case') or '') for row in image_rows])
}
summary['imageBoundaryCoverage'] = {
    'ok': (
        len(image_rows) == len(successful_case_ids)
        and all(image_case_counts.get(case_id) == 1 for case_id in successful_case_ids)
        and not any(case_id not in successful_case_ids for case_id in image_case_counts)
    ),
    'missingCases': [case_id for case_id in successful_case_ids if image_case_counts.get(case_id, 0) == 0],
    'duplicateCases': [case_id for case_id, count in sorted(image_case_counts.items()) if count > 1],
    'unexpectedCases': [case_id for case_id in sorted(image_case_counts) if case_id not in successful_case_ids],
}
summary['logicalTransportErrors'] = [
    {
        'sequence': row.get('sequence'),
        'case': row.get('case'),
        'caseIndex': row.get('caseIndex'),
        'llmStage': row.get('llmStage'),
        'error': row.get('error'),
    }
    for row in logical_rows
    if row.get('phase') == 'error' and row.get('transportError')
]
summary['logicalNonTransportErrors'] = [
    {
        'sequence': row.get('sequence'),
        'llmStage': row.get('llmStage'),
        'error': row.get('error'),
    }
    for row in logical_rows
    if row.get('phase') == 'error' and not row.get('transportError')
]
summary.update(
    transport_retry_summary(
        logical_rows,
        logical_requests=global_counts['logicalRequests'],
        http_requests=global_counts['httpRequests'],
    )
)
summary.update(case_transport_retry_report(logical_rows, harness_rows))
summary['caseTransportRetryAccountingConsistent'] = (
    transport_failures == summary['caseTransportRetryCount']
    == sum(int(row.get('caseTransportRetries') or 0) for row in result_rows)
)
summary['requireZeroTransportRetries'] = bool(args.require_zero_transport_retries)
expected_peak_crafts = min(args.parallel_crafts, len(selected_cases))
summary['concurrencyCoverage'] = {
    'ok': (
        global_counts['activeCrafts'] == 0
        and global_counts['activeLogical'] == 0
        and global_counts['activeHttp'] == 0
        and global_counts['peakActiveCrafts'] == expected_peak_crafts
        and global_counts['peakActiveLogical'] <= args.parallel_crafts
        and global_counts['peakActiveHttp'] <= args.parallel_crafts
    ),
    'expectedPeakCrafts': expected_peak_crafts,
    'observedPeakCrafts': global_counts['peakActiveCrafts'],
    'observedPeakLogical': global_counts['peakActiveLogical'],
    'observedPeakHttp': global_counts['peakActiveHttp'],
}
summary['failedCases'] = [str(row.get('case') or '') for row in result_rows if not row.get('ok')]
summary['firstAuthorSuccesses'] = sum(1 for row in result_rows if row.get('ok') and row.get('firstAuthorSuccess'))
summary['repairFreeSuccesses'] = summary['firstAuthorSuccesses']
summary['requiredFirstAuthorSuccesses'] = args.min_first_author
summary['authorBudgetViolations'] = [
    str(row.get('case') or '') for row in result_rows if not row.get('authorCallBudgetValid')
]
summary['ok'] = (
    not summary['failedCases']
    and not summary['authorBudgetViolations']
    and not summary['unaccountedTransportErrors']
    and not summary['logicalNonTransportErrors']
    and summary['caseAttemptCoverage']
    and summary['retryWaitCoverage']
    and summary['caseTransportRetryAccountingConsistent']
    and summary['transportRetryAccountingConsistent']
    and summary['transportRetryCount'] == 0  # No fast hidden retries; explicit paced retries are counted separately.
    and summary['concurrencyCoverage']['ok']
    and len(result_rows) == len(selected_cases)
    and summary['imageBoundaryCoverage']['ok']
    and summary['firstAuthorSuccesses'] >= args.min_first_author
)
(OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False), flush=True)
if not summary['ok']:
    raise SystemExit(1)
