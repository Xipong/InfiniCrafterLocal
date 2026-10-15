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
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'tkinter' or fullname.startswith('tkinter.'):
            raise AssertionError('Tk must not be imported')
sys.meta_path.insert(0, RejectTk())
from pathlib import Path
from infini_local.desktop.settings_controller import SettingsController
from infini_local.desktop.web_studio import StudioController, StudioServer
app = SettingsController(Path(sys.argv[1]))
server = StudioServer(Path('.'))
controller = StudioController(app, server)
assert controller.snapshot()['fields']
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
    app, controller = studio
    app.values['INFINI_LLM_PROVIDER'] = provider
    app.codex_efforts = ['off', 'high']
    field = next(row for row in controller.snapshot()['fields'] if row['key'] == 'INFINI_LLM_REASONING_MODE')
    assert {'auto', 'tokens', 'prompt_light', 'prompt_strong'} <= set(field['options'])
    # Codex-specific filtering is derived by each browser from its draft model,
    # not from the most recent provider selection in the shared controller.
    assert app.codex_efforts == ['off', 'high']


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
