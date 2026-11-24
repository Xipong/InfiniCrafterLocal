"""No-image Live campaign observers. Importing does not start a campaign."""
from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from infini_local.qa.live_no_image_fixture import (
    hydrate_no_image_fixture_assets, observe_no_image_readiness, write_no_image_fixture_png,
)


def create_fixture(sprite_dir: Path) -> Path:
    # Delivery transfers PNGs by basename from canonical serving roots, not OUT.
    return write_no_image_fixture_png(sprite_dir / 'qa-no-image-fixture.png')


def capture_image_boundary(data: dict[str, Any], pending: Any = None, *,
                           fixture: Path, emit: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    from infini_local.pipelines.images.prompts import asset_negative_prompt, normalize_asset_prompt
    from infini_local.pipelines.visual.assets import build_visual_asset_plan

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
        final_prompt = raw_prompt
        if should_call:
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

    emit({
        'qaFixturePath': str(fixture),
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
    return hydrate_no_image_fixture_assets(data, fixture)


def install_readiness_observers(pipeline: Any, fixture: Path) -> None:
    original_cached_payload_report = pipeline._cached_payload_report
    original_assert_visual_delivery_ready = pipeline.assert_visual_delivery_ready

    def no_image_cached_payload_report(data: Any) -> dict[str, Any]:
        from infini_local.pipelines.visual.delivery import VisualDeliveryBlocked

        try:
            if not isinstance(data, dict):
                return original_cached_payload_report(data)
            control, report = observe_no_image_readiness(data, fixture, original_cached_payload_report)
        except VisualDeliveryBlocked as exc:
            if not str(exc).startswith('qa_fixture_identity_changed:'):
                raise
            return {
                'ok': False,
                'errors': [{'path': '$.visual', 'code': 'qa_fixture_identity_changed', 'message': str(exc)}],
                'visual': {'ok': False, 'problems': [{'code': 'qa_fixture_identity_changed', 'message': str(exc)}]},
                'noImageExecutionControl': {'kind': 'synthetic_no_image_execution_control', 'synthetic': True,
                                            'realImageGeneration': False, 'owners': []},
            }
        if isinstance(control, dict):
            report['noImageExecutionControl'] = copy.deepcopy(control.get('debug', {}).get('noImageExecutionControl'))
        return report

    def no_image_assert_visual_delivery_ready(data: dict[str, Any]) -> dict[str, Any]:
        # Real early gate, on the same explicitly synthetic/private execution copy
        # as final/cache readiness. Never return or persist its generated statuses.
        observe_no_image_readiness(data, fixture, original_assert_visual_delivery_ready)
        return data

    pipeline._cached_payload_report = no_image_cached_payload_report
    pipeline.assert_visual_delivery_ready = no_image_assert_visual_delivery_ready
