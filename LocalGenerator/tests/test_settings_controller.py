"""Real headless control-plane tests; no fake widgets or DISPLAY dependency."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

import pytest

from infini_local.desktop.settings_controller import SettingsController
from infini_local.desktop.settings_env import CUSTOM_PRESET, USER_PRESET_PREFIX, parse_env, write_env
from infini_local.desktop.settings_schema import DEFAULTS, PRESETS
from infini_local.desktop.web_studio import StudioController, StudioServer


@pytest.fixture
def studio(tmp_path):
    config = tmp_path / 'config.env'
    write_env(config, dict(DEFAULTS, INFINI_CACHE_DIR=str(tmp_path / 'cache')))
    app = SettingsController(config)
    server = StudioServer(Path(__file__).parents[1] / 'infini_local' / 'desktop' / 'webui')
    controller = StudioController(app, server)
    yield app, controller
    app.on_close()
    server.close()


def apply(controller, action, values=None, extra=None):
    identifier = str(len(controller.action_results))
    controller.apply({'id': identifier, 'action': action, 'values': values or {}, 'extra': extra or {}})
    return controller.action_results[identifier]


def test_real_controller_import_and_run_without_tk_or_display(tmp_path):
    code = '''
import importlib.abc, sys
class RejectTk(importlib.abc.MetaPathFinder):
    forbid_bootstrap = True
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {'tkinter', '_tkinter'} or fullname.startswith('tkinter.'):
            raise AssertionError('Tk must not be imported')
        if self.forbid_bootstrap and (fullname in {'infini_local.core.config_bootstrap', 'infini_local.web.server'} or fullname.startswith('infini_local.pipelines.')):
            raise AssertionError('Studio must not bootstrap the generation backend: ' + fullname)
guard = RejectTk()
sys.meta_path.insert(0, guard)
from pathlib import Path
from infini_local.desktop.settings_controller import SettingsController
from infini_local.desktop.web_studio import StudioController, StudioServer
app = SettingsController(Path(sys.argv[1]))
# Existing snapshot version lookup may bootstrap config; plain Studio imports must not.
guard.forbid_bootstrap = False
server = StudioServer(Path('.'))
controller = StudioController(app, server)
assert isinstance(app.values, dict)
state = controller.snapshot()
assert state['fields'] and state['values']
app.after(0, lambda: setattr(app, 'status', 'scheduled'))
app.pump()
assert app.status == 'scheduled'
app.on_close()
server.close()
'''
    env = dict(os.environ)
    env.pop('DISPLAY', None)
    env['PYTHONPATH'] = str(Path(__file__).parents[1])
    subprocess.run([sys.executable, '-c', code, str(tmp_path / 'config.env')], env=env, check=True, timeout=15)


def test_snapshot_does_not_certify_unsaved_values(studio):
    app, controller = studio
    app.values['INFINI_PORT'] = '9091'
    snap = controller.snapshot()
    assert snap['values']['INFINI_PORT'] == '9091'
    assert snap['savedValues']['INFINI_PORT'] == DEFAULTS['INFINI_PORT']


def test_stale_revision_rejected_before_any_mutation(studio):
    app, controller = studio
    before = dict(app.values)
    revision = controller.snapshot()['savedRevision']
    app.config_path.write_text(app.config_path.read_text() + '\n# changed\n')
    with pytest.raises(ValueError, match='другой вкладке'):
        apply(controller, 'save', {'INFINI_PORT': '9192'}, {'savedRevision': revision})
    assert app.values == before
    assert controller.last_action['status'] == 'failed'


def test_save_unknown_values_and_multiline_codec(studio):
    app, controller = studio
    result = apply(controller, 'save', {'INFINI_CUSTOM_EXTENSION': 'a\nb="quoted"', 'INFINI_SDCPP_SERVER_EXTRA_ARGS': '--foo\n  bar'})
    assert result['saved']
    saved = parse_env(app.config_path)
    assert saved['INFINI_CUSTOM_EXTENSION'] == 'a\nb="quoted"'
    assert saved['INFINI_SDCPP_SERVER_EXTRA_ARGS'] == '--foo bar'


def test_removed_disk_extension_not_resurrected(studio):
    app, controller = studio
    app.values['INFINI_REMOVED_EXTENSION'] = 'stale'
    apply(controller, 'save', {'INFINI_PORT': '5055'})
    assert 'INFINI_REMOVED_EXTENSION' not in parse_env(app.config_path)


def test_profile_saved_without_secrets_or_config_write(studio):
    app, controller = studio
    before = app.config_path.read_bytes()
    result = apply(controller, 'savePreset', {'INFINI_EXTENSION': 'extra', 'INFINI_OPENROUTER_API_KEY': 'never-copy'}, {'name': 'Headless profile'})
    profile = json.loads(app.config_path.with_name('gui_user_presets.json').read_text())
    assert 'never-copy' not in json.dumps(profile)
    assert result['values']['INFINI_EXTENSION'] == 'extra'
    assert result['values']['INFINI_GUI_PIPELINE_PRESET'] == USER_PRESET_PREFIX + 'Headless profile'
    assert app.config_path.read_bytes() == before
    assert 'INFINI_EXTENSION' not in app.values


def test_profile_transform_returns_values_without_mutating_other_tabs(studio):
    app, controller = studio
    app.user_presets['Laptop'] = {'INFINI_EXTENSION': 'from profile', 'INFINI_SDCPP_LORA_PROMPT_TAGS': 'disabled multiline'}
    before = dict(app.values)
    result = apply(controller, 'applyPreset', {'INFINI_PORT': '7171'}, {'name': USER_PRESET_PREFIX + 'Laptop'})
    assert result['values']['INFINI_EXTENSION'] == 'from profile'
    assert result['values']['INFINI_SDCPP_LORA_PROMPT_TAGS'] == 'disabled multiline'
    assert app.values == before


def test_builtin_profile_preserves_explicit_resize_preferences(studio):
    app, controller = studio
    result = apply(controller, 'applyPreset', {'INFINI_SPRITE_DOWNSCALE_FILTER': 'lanczos'}, {'name': next(iter(PRESETS))})
    assert result['values']['INFINI_SPRITE_DOWNSCALE_FILTER'] == 'lanczos'


def test_lora_windows_path_and_unselected_clear(studio):
    app, controller = studio
    result = apply(controller, 'useLora', {'INFINI_SDCPP_LORA_FILE': r'C:\models\lora\ink.safetensors', 'INFINI_SDCPP_LORA_WEIGHT': '0.35'})
    assert result['values']['INFINI_SDCPP_LORA_DIR'] == r'C:\models\lora'
    assert result['values']['INFINI_SDCPP_LORA_PROMPT_TAGS'] == '<lora:ink:0.35>'
    assert not app.values['INFINI_SDCPP_LORA_FILE']
    app.values['INFINI_SDCPP_LORA_DIR'] = 'stale'
    assert app.collect()['INFINI_SDCPP_LORA_DIR'] == ''


@pytest.mark.parametrize('path,directory,stem,weight,expected_weight', [
    (r'C:\models\lora\ink.safetensors', r'C:\models\lora', 'ink', '0.35', '0.35'),
    ('C:/models/lora/ink.ckpt', r'C:\models\lora', 'ink', '', '0.25'),
    (r'\\model-share\art\loras\ink.safetensors', r'\\model-share\art\loras', 'ink', '  ', '0.25'),
    ('/models/loras/ink.safetensors', '/models/loras', 'ink', ' 0.45 ', '0.45'),
    ('ink.safetensors', '.', 'ink', '', '0.25'),
    (' relative/ink art.ckpt ', 'relative', 'ink art', '-0.5', '-0.5'),
])
def test_lora_collect_and_use_preserve_path_and_weight_semantics(studio, path, directory, stem, weight, expected_weight):
    app, controller = studio
    selected = {'INFINI_SDCPP_LORA_FILE': path, 'INFINI_SDCPP_LORA_WEIGHT': weight,
                'INFINI_SDCPP_LORA_PROMPT_TAGS': ''}
    tag = f'<lora:{stem}:{expected_weight}>'
    result = apply(controller, 'useLora', selected)
    assert result['values']['INFINI_SDCPP_LORA_DIR'] == directory
    assert result['values']['INFINI_SDCPP_LORA_PROMPT_TAGS'] == tag
    app.values.update(selected)
    collected = app.collect()
    assert collected['INFINI_SDCPP_LORA_DIR'] == directory
    assert collected['INFINI_SDCPP_LORA_PROMPT_TAGS'] == tag
    app.values['INFINI_SDCPP_LORA_PROMPT_TAGS'] = tag + ' <lora:other:0.2>'
    app.use_selected_lora()
    assert app.values['INFINI_SDCPP_LORA_PROMPT_TAGS'] == tag + ' <lora:other:0.2>'


@pytest.mark.parametrize('lan,transport,host', [(True,'native','127.0.0.1'), (True,'http','0.0.0.0'), (False,'http','127.0.0.1')])
def test_lan_overlay_only_exposes_http_asset_transport(studio, lan, transport, host):
    app, _ = studio
    app.values.update(INFINI_MP_ASSET_TRANSPORT=transport, INFINI_HOST='0.0.0.0')
    app.lan_enabled = lan
    assert app.collect()['INFINI_HOST'] == host


def test_config_preview_masks_unknown_credentials(studio):
    app, controller = studio
    write_env(app.config_path, dict(DEFAULTS, INFINI_CUSTOM_CREDENTIAL='hidden', INFINI_PUBLIC_VALUE='visible'))
    content = apply(controller, 'openConfig')['result']['content']
    assert 'hidden' not in content
    assert 'visible' in content
    assert '••••••••' in content


def test_scheduler_cancellation_and_fairness(studio):
    app, _ = studio
    calls = []
    cancelled = app.after(0, lambda: calls.append('bad'))
    app.after_cancel(cancelled)
    def repeat():
        calls.append('ok')
        app.after(0, repeat)
    app.after(0, repeat)
    app.pump()
    assert 1 <= len(calls) <= 64
    assert 'bad' not in calls
    app.cancel_scheduled()
    before = len(calls)
    app.pump()
    assert len(calls) == before


def test_exit_publishes_closed_state(studio):
    app, controller = studio
    controller.server.publish(controller.snapshot())
    controller.server.commands.put({'id': 'exit', 'action': 'exitStudio', 'values': {}, 'extra': {}})
    controller.tick()
    assert app._gui_closed
    assert controller.server._state['closed']
    assert controller.server._state['lastAction']['status'] == 'succeeded'
    assert not controller.server.accepting_actions


def test_external_extension_edit_survives_partial_save(studio):
    app, controller = studio
    app.values['INFINI_EXTERNAL_EXTENSION'] = 'old cached value'
    write_env(app.config_path, dict(DEFAULTS, INFINI_EXTERNAL_EXTENSION='new disk value'))
    apply(controller, 'save', {'INFINI_PORT': '6060'})
    assert parse_env(app.config_path)['INFINI_EXTERNAL_EXTENSION'] == 'new disk value'


@pytest.mark.parametrize('provider', ['local', 'openrouter', 'openai_compat', 'openai_codex'])
def test_shared_snapshot_retains_generic_reasoning_choices_for_each_tab(studio, provider):
    from infini_local.desktop.settings_fields import FIELDS
    from infini_local.services.codex_catalog import CodexModel

    app, controller = studio
    app._codex_text_models = {'narrow-model': CodexModel('narrow-model', 'Narrow', ('high',), 'high', 1)}
    app.update_values({'INFINI_LLM_PROVIDER': provider, 'INFINI_CODEX_LLM_MODEL': 'narrow-model',
                       'INFINI_LLM_REASONING_MODE': 'prompt_light', 'INFINI_CODEX_VISUAL_REASONING': 'max'})
    snapshot = controller.snapshot()
    for key in ('INFINI_LLM_REASONING_MODE', 'INFINI_CODEX_VISUAL_REASONING'):
        field = next(row for row in snapshot['fields'] if row['key'] == key)
        generic = next(row for row in FIELDS if row['key'] == key)
        assert field['options'] == generic['options']
    # Filtering belongs to each browser's draft; the shared model must not
    # restrict choices or rewrite unsupported preferences in another tab.
    assert snapshot['account']['textModels'] == {'narrow-model': {'efforts': ['high'], 'defaultEffort': 'high'}}
    assert snapshot['values']['INFINI_LLM_REASONING_MODE'] == 'prompt_light'
    assert snapshot['values']['INFINI_CODEX_VISUAL_REASONING'] == 'max'


@pytest.mark.parametrize('through_bridge', [False, True])
def test_save_preserves_opaque_extension_whitespace(studio, through_bridge):
    app, controller = studio
    value = '  prefix\n  body\n'
    disk = parse_env(app.config_path)
    disk['INFINI_EXTENSION_TEMPLATE'] = value
    write_env(app.config_path, disk)
    app.values['INFINI_EXTENSION_TEMPLATE'] = value
    if through_bridge:
        apply(controller, 'save', {'INFINI_PORT': ' 5055 '})
    else:
        app.values['INFINI_PORT'] = ' 5055 '
        app.save()
    saved = parse_env(app.config_path)
    assert saved['INFINI_EXTENSION_TEMPLATE'] == value
    assert saved['INFINI_PORT'] == '5055'


def test_parallel_image_checkbox_round_trips_saved_config(studio):
    app, controller = studio
    assert controller.snapshot()['values']['INFINI_IMAGE_PARALLEL'] == '1'
    for enabled in ('0', '1', '0'):
        result = apply(controller, 'save', {'INFINI_IMAGE_PARALLEL': enabled, 'INFINI_IMAGE_MAX_CONCURRENCY': '4'})
        assert result['saved']
        saved = parse_env(app.config_path)
        assert saved['INFINI_IMAGE_PARALLEL'] == enabled
        assert saved['INFINI_IMAGE_MAX_CONCURRENCY'] == '4'
        reloaded = SettingsController(app.config_path)
        try:
            assert reloaded.values['INFINI_IMAGE_PARALLEL'] == enabled
            assert reloaded.values['INFINI_IMAGE_MAX_CONCURRENCY'] == '4'
        finally:
            reloaded.on_close()


def test_stock_and_hybrid_arguments_preserve_paths_and_custom_profile(studio):
    app, controller = studio
    paths = {key: '/chosen/' + key for key in (
        'INFINI_SDCPP_SERVER_EXE', 'INFINI_SDCPP_MODEL', 'INFINI_SDCPP_VAE',
        'INFINI_SDCPP_LLM', 'INFINI_SDCPP_ROCM_COMPAT_ROOT')}
    custom = dict(paths, INFINI_SDCPP_SERVER_EXTRA_ARGS=' --my-exact "two words" ', INFINI_LLM_PROVIDER='openrouter')
    original = app.config_path.read_bytes()
    saved = apply(controller, 'savePreset', custom, {'name': 'My flags'})
    assert saved['ok']
    preset_path = app.config_path.with_name('gui_user_presets.json')
    before = preset_path.read_bytes()
    for name in ('Пример: RX 6800 XT / FLUX.2 Klein 4B (только аргументы)',):
        result = apply(controller, 'applyPreset', custom, {'name': name})
        assert result['ok']
        assert all(result['values'][key] == val for key, val in paths.items())
        assert result['values']['INFINI_LLM_PROVIDER'] == 'openrouter'
        assert result['values']['INFINI_SDCPP_SERVER_EXTRA_ARGS'] == PRESETS[name]['INFINI_SDCPP_SERVER_EXTRA_ARGS']
        assert app.config_path.read_bytes() == original
        assert preset_path.read_bytes() == before
    loaded = SettingsController(app.config_path)
    try:
        assert loaded.user_presets['My flags']['INFINI_SDCPP_SERVER_EXTRA_ARGS'] == custom['INFINI_SDCPP_SERVER_EXTRA_ARGS']
    finally:
        loaded.on_close()
    for consent in (None, False, 'true', 1):
        with pytest.raises(ValueError):
            apply(controller, 'savePreset', {'INFINI_SDCPP_SERVER_EXTRA_ARGS': '--changed'}, {'name': 'My flags', 'overwrite': consent})
    assert preset_path.read_bytes() == before
    accepted = apply(controller, 'savePreset', {'INFINI_SDCPP_SERVER_EXTRA_ARGS': '--changed'}, {'name': 'My flags', 'overwrite': True})
    assert accepted['ok']
    assert app.config_path.read_bytes() == original


def test_universal_local_preset_preserves_selected_models(studio):
    app, controller = studio
    selected = {key: '/chosen/' + key for key in ('INFINI_SDCPP_MODEL', 'INFINI_SDCPP_VAE', 'INFINI_SDCPP_LLM', 'INFINI_SDCPP_SERVER_EXE')}
    selected.update(INFINI_SDCPP_ROCM_COMPAT_ROOT='/chosen/rocm', INFINI_SDCPP_SERVER_EXTRA_ARGS='--custom', INFINI_SDCPP_SERVER_COMMAND_MODE='template')
    result = apply(controller, 'applyPreset', dict(selected, INFINI_LLM_PROVIDER='openrouter'), {'name': 'Локалка: LM Studio + sd.cpp (универсальный)'})
    assert result['ok']
    assert all(result['values'][key] == val for key, val in selected.items())
    assert result['values']['INFINI_LLM_PROVIDER'] == 'local'
    assert result['values']['INFINI_SDCPP_SERVER_EXTRA_ARGS'] == '--custom'
    assert result['values']['INFINI_SDCPP_ROCM_COMPAT_ROOT'] == '/chosen/rocm'


@pytest.mark.parametrize('name,provider,backend', [
    ('Локалка: LM Studio + sd.cpp (универсальный)', 'local', 'sdcpp'),
    ('API (OpenAI-compatible) + локальные изображения sd.cpp', 'openai_compat', 'sdcpp'),
    ('API (OpenAI-compatible) + Image API', 'openai_compat', 'image_api'),
    ('ChatGPT / Codex: текст и изображения', 'openai_codex', 'openai_codex'),
])
def test_pipeline_presets_select_only_chain_and_keep_user_assets(studio, name, provider, backend):
    app, controller = studio
    owned = {key: '/chosen/' + key for key in (
        'INFINI_SDCPP_MODEL', 'INFINI_SDCPP_VAE', 'INFINI_SDCPP_LLM', 'INFINI_SDCPP_SERVER_EXE',
        'INFINI_SDCPP_LORA_FILE', 'INFINI_OPENAI_COMPAT_BASE_URL', 'INFINI_IMAGE_API_BASE_URL',
        'INFINI_OPENAI_COMPAT_MODEL', 'INFINI_CODEX_LLM_MODEL', 'INFINI_CODEX_IMAGE_MODEL')}
    owned.update(INFINI_SDCPP_STEPS='23', INFINI_SDCPP_CFG='2.5', INFINI_LLM_API_MODE='responses',
                 INFINI_SDCPP_ROCM_COMPAT_ROOT='/chosen/rocm', INFINI_SDCPP_SERVER_EXTRA_ARGS='--my-flags',
                 INFINI_SDCPP_SERVER_COMMAND_MODE='template')
    apply(controller, 'savePreset', owned, {'name': '123'})
    profiles = app.config_path.with_name('gui_user_presets.json')
    before, config_before = profiles.read_bytes(), app.config_path.read_bytes()
    saved_profile = dict(app.user_presets['123'])
    result = apply(controller, 'applyPreset', owned, {'name': name})
    assert result['ok']
    assert (result['values']['INFINI_LLM_PROVIDER'], result['values']['INFINI_IMAGE_BACKEND']) == (provider, backend)
    assert all(result['values'][key] == value for key, value in owned.items())
    assert profiles.read_bytes() == before and app.config_path.read_bytes() == config_before
    assert app.user_presets['123'] == saved_profile


def test_retired_profile_identity_does_not_rewrite_or_mislabel_settings():
    data = {'INFINI_GUI_PIPELINE_PRESET': 'Локалка: LM Studio + FLUX.2 Klein 4B hybrid',
            'INFINI_LLM_PROVIDER': 'local', 'INFINI_IMAGE_BACKEND': 'sdcpp',
            'INFINI_SDCPP_MODEL': '/my/model', 'INFINI_SDCPP_SERVER_EXTRA_ARGS': '--my-flags'}
    original = dict(data)
    assert SettingsController._pipeline_preset_from_config(data) == 'Custom'
    assert data == original
