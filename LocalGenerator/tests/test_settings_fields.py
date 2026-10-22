"""Behavioral coverage for browser metadata independent of a display toolkit."""
from copy import deepcopy

from infini_local.desktop.settings_fields import FIELDS, disabled_reasons
from infini_local.desktop.settings_schema import DEFAULTS


def test_metadata_preserves_secret_multiline_and_independent_pool_controls():
    fields = {field['key']: field for field in FIELDS}
    assert len(fields) == len(FIELDS)
    for slot in (2, 3, 4):
        key = f'INFINI_LLM_POOL_{slot}_API_KEY'
        assert fields[key]['secret'] is True
        assert fields[key]['page'] == 'models'
        assert fields[f'INFINI_LLM_POOL_{slot}_PROVIDER']['options'] == ['local', 'openrouter', 'openai_compat']
    assert fields['INFINI_SDCPP_SERVER_EXTRA_ARGS']['multiline'] is True
    assert fields['INFINI_SDCPP_LORA_PROMPT_TAGS']['multiline'] is True
    assert fields['INFINI_OPENAI_COMPAT_API_KEY']['secret'] is True
    assert fields['INFINI_LLM_MAX_TOKENS']['secret'] is False
    assert fields['INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED']['options'] == ['1', '0']


def test_codex_disables_unsupported_parameters_without_rewriting_values():
    values = {**DEFAULTS, 'INFINI_LLM_PROVIDER': 'openai_codex', 'INFINI_LLM_MAX_TOKENS': '18000',
              'INFINI_VISUAL_STRICT_AI_AUTHORSHIP': '1', 'INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK': '1'}
    original = deepcopy(values)
    reasons = disabled_reasons(values)
    assert reasons['INFINI_LLM_MAX_TOKENS']
    assert reasons['INFINI_LLM_TEMPERATURE']
    assert reasons['INFINI_LLM_REASONING_EXCLUDE']
    assert not reasons['INFINI_CODEX_LLM_MODEL']
    assert values == original


def test_native_alpha_keeps_background_and_alpha_controls_usable():
    reasons = disabled_reasons({**DEFAULTS, 'INFINI_IMAGE_BACKEND': 'sdcpp', 'INFINI_BG_COLOR': 'transparent'})
    assert reasons['INFINI_REMOVE_BG']
    assert reasons['INFINI_CHROMA_TOLERANCE']
    assert not reasons['INFINI_BG_COLOR']
    assert not reasons['INFINI_ALPHA_THRESHOLD']


def test_http_asset_url_requires_both_transport_and_lan_overlay():
    values = {**DEFAULTS, 'INFINI_MP_ASSET_TRANSPORT': 'http'}
    assert disabled_reasons(values, False)['INFINI_ASSET_PUBLIC_BASE_URL']
    assert not disabled_reasons(values, True)['INFINI_ASSET_PUBLIC_BASE_URL']
    assert disabled_reasons({**values, 'INFINI_MP_ASSET_TRANSPORT': 'native'}, True)['INFINI_ASSET_PUBLIC_BASE_URL']


def test_upstream_pinning_requires_enabled_openrouter_profile():
    values = {**DEFAULTS, 'INFINI_LLM_POOL_2_ENABLED': '1', 'INFINI_LLM_POOL_2_PROVIDER': 'openrouter'}
    assert not disabled_reasons(values)['INFINI_LLM_POOL_2_OPENROUTER_PROVIDER']
    assert disabled_reasons({**values, 'INFINI_LLM_POOL_2_ENABLED': '0'})['INFINI_LLM_POOL_2_OPENROUTER_PROVIDER']
    assert disabled_reasons({**values, 'INFINI_LLM_POOL_2_PROVIDER': 'local'})['INFINI_LLM_POOL_2_OPENROUTER_PROVIDER']


def test_parallel_images_default_on_basic_checkbox_preserves_disabled_limit():
    fields = {field['key']: field for field in FIELDS}
    field = fields['INFINI_IMAGE_PARALLEL']
    assert DEFAULTS['INFINI_IMAGE_PARALLEL'] == '1'
    assert DEFAULTS['INFINI_IMAGE_MAX_CONCURRENCY'] == '4'
    assert field['options'] == ['1', '0']
    assert field['page'] == 'images' and not field['advanced']
    assert not fields['INFINI_IMAGE_MAX_CONCURRENCY']['advanced']
    assert 'видеопамять' in field['help']
    assert '2–4' in field['help']
    assert 'не будут выполняться одновременно с VFX Designer' in field['help']
    values = {**DEFAULTS, 'INFINI_IMAGE_PARALLEL': '0', 'INFINI_IMAGE_MAX_CONCURRENCY': '4'}
    original = deepcopy(values)
    assert not disabled_reasons(values)['INFINI_IMAGE_PARALLEL']
    assert disabled_reasons(values)['INFINI_IMAGE_MAX_CONCURRENCY']
    assert values == original
    assert not disabled_reasons({**values, 'INFINI_IMAGE_PARALLEL': '1'})['INFINI_IMAGE_MAX_CONCURRENCY']
    assert disabled_reasons({**values, 'INFINI_IMAGE_BACKEND': 'off'})['INFINI_IMAGE_PARALLEL']
