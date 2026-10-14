from __future__ import annotations

"""Loopback-only browser Studio and main-thread adapter for the desktop controller.

HTTP workers exchange immutable JSON snapshots and queued commands only. Existing
safe restart, profile, OAuth and trace owners stay on the Tk main thread.
"""

import argparse
import copy
from collections import OrderedDict
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import re
import secrets
import stat
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

from infini_local.desktop.tk_compat import tk
from infini_local.desktop.settings_interactions import saved_config_revision

ACTIONS = frozenset({
    'save', 'start', 'stop', 'health', 'validate', 'trace', 'applyPreset', 'savePreset',
    'codexLogin', 'codexStatus', 'codexCatalog', 'codexPing', 'clearLora', 'useLora',
    'resetSprite', 'openConfig', 'openCache', 'clearTrace', 'browse', 'help', 'exitStudio',
    'forceRestart', 'cancelTrace', 'codexLogout', 'acceptDefaults', 'declineDefaults',
})
STATIC_FILES = {'/studio.css': ('studio.css', 'text/css; charset=utf-8'),
                '/studio.js': ('studio.js', 'text/javascript; charset=utf-8')}


class StudioServer:
    def __init__(self, assets: Path, *, port: int = 0):
        self.assets = assets
        self.token = secrets.token_urlsafe(32)
        from infini_local.desktop.settings_gui_theme import ROOT
        self.file_root = ROOT
        self.commands: queue.Queue[dict] = queue.Queue(maxsize=32)
        self.accepting_actions = True
        self._lock = threading.Lock()
        self._state: dict = {'status': 'Starting Studio', 'values': {}}
        self._thread: threading.Thread | None = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                # Never log token-bearing URLs or configuration payloads.
                return

            def reply(self, code, payload, content_type='application/json; charset=utf-8'):
                data = json.dumps(payload, ensure_ascii=False).encode() if isinstance(payload, dict) else payload
                self.send_response(code)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def authorized(self, *, bootstrap=False):
                host = self.headers.get('Host', '')
                port = owner.httpd.server_port
                if host not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
                    return False
                origin = self.headers.get('Origin')
                if origin and origin not in {owner.base_url, f'http://localhost:{port}'}:
                    return False
                supplied = self.headers.get('X-Infini-Token', '')
                if bootstrap:
                    supplied = parse_qs(urlsplit(self.path).query).get('token', [''])[0]
                return secrets.compare_digest(supplied, owner.token)

            def do_GET(self):
                path = urlsplit(self.path).path
                if path == '/guide':
                    if not (self.authorized() or self.authorized(bootstrap=True)):
                        self.reply(403, {'error': 'Session access required'})
                        return
                    try:
                        guide = (owner.file_root.parent / 'START_HERE.html').read_bytes()
                        self.reply(200, guide, 'text/html; charset=utf-8')
                    except OSError:
                        self.reply(404, {'error': 'Локальная инструкция не найдена'})
                elif path == '/api/files':
                    if not self.authorized():
                        self.reply(403, {'error': 'Session access required'})
                        return
                    query = parse_qs(urlsplit(self.path).query)
                    try:
                        listing = owner.list_files(query.get('path', [''])[0], query.get('kind', ['file'])[0])
                        self.reply(200, listing)
                    except (OSError, ValueError):
                        self.reply(400, {'error': 'Не удалось прочитать папку. Проверь путь и права доступа.'})
                elif path == '/api/state':
                    if not self.authorized():
                        self.reply(403, {'error': 'Session access required'})
                        return
                    with owner._lock:
                        state = copy.deepcopy(owner._state)
                    self.reply(200, state)
                elif path in {'/', '/index.html'}:
                    if not self.authorized(bootstrap=True):
                        self.reply(403, {'error': 'Open Studio from its local launcher'})
                        return
                    try:
                        html = (owner.assets / 'index.html').read_text(encoding='utf-8')
                    except OSError:
                        self.reply(503, {'error': 'Studio interface files are missing'})
                        return
                    bootstrap = '<script>window.INFINI_BOOTSTRAP=' + json.dumps({'token': owner.token}) + ';</script>'
                    html = html.replace('</head>', bootstrap + '</head>')
                    self.reply(200, html.encode(), 'text/html; charset=utf-8')
                elif path in STATIC_FILES or path.startswith('/assets/'):
                    if path in STATIC_FILES:
                        filename, kind = STATIC_FILES[path]
                    else:
                        filename = path.lstrip('/')
                        extension = Path(filename).suffix.lower()
                        kind = {'.woff2': 'font/woff2', '.woff': 'font/woff', '.svg': 'image/svg+xml',
                                '.png': 'image/png', '.webp': 'image/webp'}.get(extension)
                        target = (owner.assets / filename).resolve()
                        if kind is None or not target.is_relative_to((owner.assets / 'assets').resolve()):
                            self.reply(404, {'error': 'Asset not found'})
                            return
                    try:
                        self.reply(200, (owner.assets / filename).read_bytes(), kind)
                    except OSError:
                        self.reply(404, {'error': 'Asset not found'})
                else:
                    self.reply(404, {'error': 'Route not found'})

            def do_POST(self):
                if urlsplit(self.path).path != '/api/action':
                    self.reply(404, {'error': 'Route not found'})
                    return
                if not self.authorized():
                    self.reply(403, {'error': 'Session access required'})
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 2 * 1024 * 1024:
                        self.reply(413, {'error': 'Request size limit exceeded'})
                        return
                    payload = json.loads(self.rfile.read(size))
                    action = payload.get('action') if isinstance(payload, dict) else None
                    values, extra = payload.get('values', {}), payload.get('extra', {})
                    if action not in ACTIONS or not isinstance(values, dict) or not isinstance(extra, dict):
                        raise ValueError('Invalid action')
                    if any(not isinstance(key, str) or not key.startswith('INFINI_') or not isinstance(value, str)
                           or len(key) > 160 or len(value) > 131072 for key, value in values.items()):
                        raise ValueError('Invalid settings')
                    identifier = secrets.token_hex(8)
                    with owner._lock:
                        accepting = owner.accepting_actions
                        if accepting:
                            owner.commands.put_nowait({'id': identifier, 'action': action, 'values': values, 'extra': extra})
                    if not accepting:
                        self.reply(409, {'error': 'Студия уже закрыта. Открой её заново через запускатор.'})
                        return
                    self.reply(202, {'ok': True, 'id': identifier})
                except queue.Full:
                    self.reply(429, {'error': 'Studio is busy; retry after the current operation'})
                except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
                    self.reply(400, {'error': 'Invalid action request'})

        self.httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.httpd.daemon_threads = True
        self.base_url = f'http://127.0.0.1:{self.httpd.server_port}'
        self.url = self.base_url + '/?token=' + self.token

    def list_files(self, raw_path: str, kind: str) -> dict:
        """Read-only local path chooser. Never upload or serve file contents."""
        if kind not in {'file', 'folder', 'model', 'lora'} or len(raw_path) > 4096:
            raise ValueError('Invalid file chooser request')
        # A local picker must not initiate credential-bearing UNC/network access.
        def network_path(value):
            return value.replace('\\', '/').startswith('//')
        if network_path(raw_path) or '\x00' in raw_path:
            raise ValueError('Network paths are not supported by the picker')
        path = Path(raw_path).expanduser() if raw_path else self.file_root
        if not path.is_absolute():
            path = self.file_root / path
        path = Path(os.path.abspath(path))
        if os.name == 'nt':
            # Windows mapped drives and reparse points can contact SMB without
            # an obvious UNC spelling. Reject them before traversing/statting.
            import ctypes
            if ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) == 4:
                raise ValueError('Network drives are not supported by the picker')
        for component in (*reversed(path.parents), path):
            try:
                metadata = component.lstat()
            except FileNotFoundError:
                break
            if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Linked paths are not supported by the picker')
        path = path.resolve(strict=False)
        if network_path(str(path)):
            raise ValueError('Network paths are not supported by the picker')
        requested = path
        # A saved model may have moved. Open its nearest existing parent rather
        # than trapping the chooser on the invalid initial path.
        while not path.exists() and path.parent != path:
            path = path.parent
        warning = '' if path == requested else 'Путь не найден. Показана ближайшая существующая папка.'
        selected = None
        if path.is_file():
            selectable = kind == 'file' or kind == 'model' and path.suffix.lower() in {'.gguf', '.safetensors', '.ckpt', '.pt', '.pth'} or kind == 'lora' and path.suffix.lower() in {'.safetensors', '.ckpt', '.pt', '.pth'}
            if selectable and path == requested:
                selected = {'name': path.name, 'path': str(path), 'directory': False}
            path = path.parent
        if not path.is_dir():
            raise ValueError('Directory required')
        extensions = {'.gguf', '.safetensors', '.ckpt', '.pt', '.pth'} if kind == 'model' else {'.safetensors', '.ckpt', '.pt', '.pth'}
        entries = []
        scanned = 0
        truncated = False
        with os.scandir(path) as children:
            for child in children:
                scanned += 1
                if scanned > 3000 or len(entries) >= 300:
                    truncated = True
                    break
                try:
                    directory = child.is_dir(follow_symlinks=False)
                    if child.is_symlink() or not directory and not child.is_file(follow_symlinks=False):
                        continue
                    if not directory and (kind == 'folder' or kind in {'model', 'lora'} and Path(child.name).suffix.lower() not in extensions):
                        continue
                    entries.append({'name': child.name, 'path': str(path / child.name), 'directory': directory})
                except OSError:
                    continue
        entries.sort(key=lambda item: (not item['directory'], item['name'].casefold()))
        return {'path': str(path), 'parent': str(path.parent) if path.parent != path else None,
                'entries': entries, 'truncated': truncated, 'warning': warning, 'selected': selected}

    def publish(self, state: dict) -> None:
        with self._lock:
            self._state = copy.deepcopy(state)

    def start(self) -> None:
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True, name='infini-studio-http')
        self._thread.start()

    def close(self) -> None:
        if self._thread is not None:
            self.httpd.shutdown()
            self._thread.join(timeout=3)
        self.httpd.server_close()


class StudioController:
    """Map browser commands to existing settings callbacks without worker Tk access."""
    def __init__(self, app, server: StudioServer):
        self.app, self.server = app, server
        self.fields = self._fields()
        self.last_action: dict = {}
        self.action_results: OrderedDict[str, dict] = OrderedDict()
        self.notifications: list[dict] = []
        app._ui_notification_sink = self._notify
        app._ui_action_sink = self._finish_action
        self.revision = 0
        self._saved_values: dict | None = None

    def _fields(self):
        from infini_local.desktop.settings_gui_fields import _BASIC_FIELDS
        fields = []
        pages = self.app.pages
        for key, widgets in self.app.field_widgets.items():
            page = 'configure'
            cursor = widgets[0]
            while cursor is not None:
                found = next((name for name, frame in pages.items() if cursor is frame or cursor is frame.inner), None)
                if found:
                    page = found
                    break
                cursor = getattr(cursor, 'master', None)
            label, options = key.removeprefix('INFINI_').replace('_', ' ').title(), []
            for widget in widgets:
                try:
                    text = widget.cget('text')
                    if text:
                        label = text
                        break
                except (AttributeError, TypeError, tk.TclError):
                    continue
            for widget in widgets:
                try:
                    options = list(widget.cget('values'))
                    if options:
                        break
                except (AttributeError, TypeError, tk.TclError):
                    continue
            if not options and key in self.app.vars and any(widget.winfo_class() == 'TCheckbutton' for widget in widgets):
                options = ['1', '0']
            secret = any(widget in self.app.secret_entries for widget in widgets)
            fields.append({'key': key, 'label': label, 'help': self.app.field_base_hints.get(key, ''),
                           'options': options, 'secret': secret, 'page': page,
                           'advanced': key not in _BASIC_FIELDS and not key.startswith('INFINI_LLM_POOL_'),
                           'multiline': key in self.app.text_widgets})
        return fields

    def snapshot(self):
        from itertools import islice
        from infini_local.core.config_bootstrap import APP_VERSION
        from infini_local.desktop.settings_schema import DEFAULTS, FIELD_HELP, PRESETS
        from infini_local.desktop.settings_defaults import defaults_offer
        from infini_local.desktop.settings_env import parse_env
        from infini_local.desktop.settings_gui_theme import EXAMPLE_PATH
        from infini_local.desktop.settings_gui_trace_state import CONFIG_PATH
        from infini_local.services.codex_auth import auth_status
        from infini_local.services.codex_text_backend import EFFORTS
        values = self.app._current_profile_settings()
        values['INFINI_GUI_PIPELINE_PRESET'] = self.app.preset_var.get()
        # Controller values include unsaved edits from non-saving actions. A fresh
        # browser must compare them to disk, never adopt them as a saved baseline.
        saved_error = ''
        saved_revision = None
        try:
            # Match SettingsGui startup: a fresh install loads the example.
            saved_values = parse_env(CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH)
            self._saved_values = dict(saved_values)
            saved_revision = saved_config_revision(CONFIG_PATH)
        except (OSError, ValueError, UnicodeError) as exc:
            # A transient read failure must not kill polling or certify a draft.
            saved_values = dict(self._saved_values or DEFAULTS)
            saved_error = f'Не удалось проверить сохранённую конфигурацию: {exc}'
        try:
            defaults_update = defaults_offer(CONFIG_PATH)
        except (OSError, UnicodeError, ValueError) as exc:
            # A recommendation read must not take the entire control plane down.
            defaults_update = {'changes': [], 'dismissed': True}
            saved_error = saved_error or f'Не удалось проверить рекомендации: {exc}'
        saved_values['INFINI_GUI_PIPELINE_PRESET'] = self.app._pipeline_preset_from_config(saved_values, self.app.user_presets)
        saved_lan = saved_values.get('INFINI_HOST') == '0.0.0.0' or bool(saved_values.get('INFINI_ASSET_PUBLIC_BASE_URL'))
        fields = [dict(field, disabled=self.app.field_disabled_reasons.get(field['key'], '')) for field in self.fields]
        for field in fields:
            if field['key'] == 'INFINI_CODEX_LLM_MODEL':
                field['options'] = list(self.app.codex_model_combo.cget('values'))
            elif field['key'] == 'INFINI_LLM_REASONING_MODE':
                field['options'] = list(self.app.codex_reasoning_combo.cget('values'))
            elif field['key'] == 'INFINI_CODEX_VISUAL_REASONING':
                field['options'] = list(self.app.codex_visual_reasoning_combo.cget('values'))
        # The catalog owner already validates/redacts model IDs. Publish only
        # bounded text-model metadata, so each tab can describe its own draft
        # selection without mutating the shared controller or querying providers.
        text_models = {
            model.slug: {'efforts': [effort for effort in model.efforts if effort in EFFORTS],
                         'defaultEffort': model.default_effort if model.default_effort in EFFORTS else ''}
            for model in islice(self.app.__dict__.get('_codex_text_models', {}).values(), 256)
        }
        return {
            'values': values, 'savedValues': saved_values, 'savedLanEnabled': saved_lan, 'savedRevision': saved_revision,
            'defaults': DEFAULTS, 'fieldHelp': FIELD_HELP, 'defaultsUpdate': defaults_update,
            'fields': fields, 'presets': PRESETS,
            'userPresets': self.app.user_presets, 'status': saved_error or self.app.status_var.get(),
            'activity': self.app.activity_var.get(), 'appliedConfig': self.app.applied_config_var.get(),
            'home': {'state': self.app.home_state_var.get(), 'detail': self.app.home_detail_var.get(),
                     'config': self.app.home_config_var.get()},
            'traceStatus': self.app.trace_status_var.get(),
            'notifications': self.notifications, 'actionResults': list(self.action_results.values()),
            'trace': {key: widget.get('1.0', 'end-1c') for key, widget in self.app.trace_texts.items()},
            'configPath': str(CONFIG_PATH), 'version': APP_VERSION, 'lastAction': self.last_action,
            'revision': self.revision, 'busy': list(self.app._gui_tasks), 'lanEnabled': bool(self.app.radmin_enabled.get()),
            'account': {'status': self.app.__dict__.get('_codex_account_status', ''), 'catalog': self.app.codex_catalog_var.get(),
                        'images': self.app.codex_image_account_var.get(), 'authenticated': auth_status()['authenticated'],
                        'textModels': text_models},
        }

    @staticmethod
    def _write_text(widget, value):
        # Browser drafts and their rollback may touch inactive provider fields.
        # Tk silently ignores writes while the hidden Text widget is disabled.
        previous_state = str(widget.cget('state'))
        try:
            if previous_state == 'disabled':
                widget.configure(state='normal')
            widget.delete('1.0', 'end')
            widget.insert('1.0', value)
        finally:
            if previous_state == 'disabled':
                widget.configure(state=previous_state)

    def _values(self, values, extra):
        for key, value in values.items():
            if key in self.app.vars:
                if self.app.vars[key].get() != value:
                    self.app.vars[key].set(value)
            elif key in self.app.text_widgets:
                widget = self.app.text_widgets[key]
                if widget.get('1.0', 'end-1c') != value:
                    self._write_text(widget, value)
            else:
                # The browser exposes retained extension settings explicitly.
                # Keep collect() and profile snapshots on the same existing owner.
                self.app.data[key] = value
                self.app.__dict__.setdefault('_profile_extra_settings', {})[key] = value
                if key == 'INFINI_GUI_PIPELINE_PRESET':
                    self.app.preset_var.set(value)
        if 'lanEnabled' in extra:
            self.app.radmin_enabled.set(bool(extra['lanEnabled']))
        self.app._refresh_visibility()
        if 'INFINI_CODEX_LLM_MODEL' in values:
            self.app._update_codex_efforts()

    def _notify(self, level, title, message):
        self.notifications.append({'id': secrets.token_hex(8), 'level': level, 'title': title, 'message': message,
                                   'actionId': self.app.__dict__.get('_studio_notification_action_id') or self.app.__dict__.get('_studio_command_id')})
        del self.notifications[:-64]

    def _finish_action(self, identifier, ok, message, *, cancelled=False, result=None, saved=False):
        receipt = self.action_results.get(identifier)
        if receipt is None:
            return
        self.revision += 1
        receipt.update(ok=bool(ok), status='cancelled' if cancelled else 'succeeded' if ok else 'failed',
                       message=message, revision=self.revision)
        if result is not None:
            receipt['result'] = result
        if not self.app._gui_closed and receipt['action'] in {'applyPreset', 'clearLora', 'useLora', 'resetSprite', 'savePreset', 'save', 'start', 'forceRestart'}:
            receipt['values'] = self.app._current_profile_settings()
            receipt['values']['INFINI_GUI_PIPELINE_PRESET'] = self.app.preset_var.get()
            receipt['lanEnabled'] = bool(self.app.radmin_enabled.get())
        if (ok or saved) and receipt['action'] in {'save', 'start', 'forceRestart', 'acceptDefaults'}:
            from infini_local.desktop.settings_env import parse_env
            from infini_local.desktop.settings_gui_trace_state import CONFIG_PATH
            receipt['savedValues'] = parse_env(CONFIG_PATH)
            receipt['savedValues']['INFINI_GUI_PIPELINE_PRESET'] = self.app._pipeline_preset_from_config(receipt['savedValues'], self.app.user_presets)
            receipt['savedRevision'] = saved_config_revision(CONFIG_PATH)
            receipt['saved'] = True
        self.last_action = receipt
        while len(self.action_results) > 128:
            retired = next((key for key, item in self.action_results.items() if item['status'] != 'running'), None)
            if retired is None:
                break
            del self.action_results[retired]

    def apply(self, command):
        identifier = command['id']
        self.action_results[identifier] = {'id': identifier, 'action': command['action'], 'ok': True,
                                           'status': 'running', 'message': 'Действие выполняется.'}
        self.last_action = self.action_results[identifier]
        self.app._studio_command_id = identifier
        self.app._studio_expected_config_revision = command.get('extra', {}).get('savedRevision')
        transient = command['action'] in {'health', 'trace', 'validate', 'clearTrace', 'openCache', 'stop', 'applyPreset', 'clearLora', 'useLora', 'resetSprite', 'savePreset'}
        old_values = self.app._current_profile_settings() if transient else None
        old_data = copy.deepcopy(self.app.data) if transient else None
        old_extras = copy.deepcopy(self.app.__dict__.get('_profile_extra_settings', {})) if transient else None
        old_preset = self.app.preset_var.get() if transient else None
        old_lan = self.app.radmin_enabled.get() if transient else None
        old_profile = {key: copy.deepcopy(self.app.__dict__[key]) for key in ('_profile_baseline', '_profile_baseline_label') if key in self.app.__dict__} if transient else {}
        try:
            outcome = self._apply(command)
            pending = any(task.get('command_id') == identifier or task.get('pending') and task['pending'][2] == identifier for task in self.app._gui_tasks.values())
            pending = pending or identifier in self.app.__dict__.get('_studio_async_ids', set())
            if not pending:
                outcome = outcome if isinstance(outcome, dict) else {}
                self._finish_action(identifier, outcome.get('ok', True), outcome.get('message', self.app.status_var.get() if not self.app._gui_closed else 'Студия закрыта.'),
                                    result=outcome.get('result'), saved=outcome.get('saved', False))
        except (OSError, ValueError, AttributeError, RuntimeError, tk.TclError) as exc:
            self._finish_action(identifier, False, str(exc))
            raise
        finally:
            self.app._studio_command_id = None
            self.app._studio_expected_config_revision = None
            if transient:
                # Diagnostic operations capture immutable inputs before scheduling
                # workers. Their draft must not become another tab's launch state.
                guard = self.app.__dict__.get('_profile_edit_guard', False)
                self.app._profile_edit_guard = True
                try:
                    for key, variable in self.app.vars.items():
                        if key in old_values and variable.get() != old_values[key]:
                            variable.set(old_values[key])
                    for key, widget in self.app.text_widgets.items():
                        if key in old_values and widget.get('1.0', 'end-1c') != old_values[key]:
                            self._write_text(widget, old_values[key])
                    self.app.data = old_data
                    self.app._profile_extra_settings = old_extras
                    self.app.preset_var.set(old_preset)
                    self.app.radmin_enabled.set(old_lan)
                    for key in ('_profile_baseline', '_profile_baseline_label'):
                        if key in old_profile:
                            self.app.__dict__[key] = old_profile[key]
                        else:
                            self.app.__dict__.pop(key, None)
                    self.app._refresh_visibility()
                finally:
                    self.app._profile_edit_guard = guard

    def _apply(self, command):
        from infini_local.desktop.settings_env import CUSTOM_PRESET, USER_PRESET_PREFIX, save_user_preset
        from infini_local.desktop.settings_gui_trace_state import CONFIG_PATH
        app = self.app
        action, extra = command['action'], command.get('extra', {})
        if action in {'save', 'start', 'forceRestart'} and 'savedRevision' in extra:
            if not extra['savedRevision'] or extra['savedRevision'] != saved_config_revision(CONFIG_PATH):
                raise ValueError('Конфигурация на диске изменилась в другой вкладке или программе. Черновик сохранён в этой вкладке. Проверь новые сохранённые значения перед повторным сохранением или запуском.')
        if action in {'save', 'start', 'forceRestart'}:
            from infini_local.desktop.settings_env import parse_env
            from infini_local.desktop.settings_schema import DEFAULTS
            from infini_local.desktop.settings_gui_theme import EXAMPLE_PATH
            # Retained extension keys may have been removed on disk since this
            # adapter loaded. Keep current disk keys and explicit draft edits,
            # but never resurrect an absent key from the adapter's stale cache.
            saved = parse_env(CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH)
            retained = set(DEFAULTS) | set(app.vars) | set(app.text_widgets) | set(saved) | set(command.get('values', {}))
            for cached in (app.data, app.__dict__.get('_profile_extra_settings', {})):
                for key in set(cached) - retained:
                    del cached[key]
        if action == 'clearTrace' and extra.get('confirm') is not True:
            raise ValueError('Подтверди очистку журнала в браузере.')
        if action in {'health', 'trace', 'clearTrace', 'openCache', 'stop'}:
            from infini_local.desktop.settings_env import parse_env
            from infini_local.desktop.settings_schema import DEFAULTS
            from infini_local.desktop.settings_gui_theme import EXAMPLE_PATH
            owned = app.proc is not None and app.proc.poll() is None
            saved = app.__dict__.get('_owned_launch_settings') if owned else None
            if saved is None:
                saved = parse_env(CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH)
            target = dict(DEFAULTS, **saved)
            target['INFINI_GUI_PIPELINE_PRESET'] = app._pipeline_preset_from_config(target, app.user_presets)
            self._values(target, {'lanEnabled': target.get('INFINI_HOST') == '0.0.0.0' or bool(target.get('INFINI_ASSET_PUBLIC_BASE_URL'))})
        elif action not in {'acceptDefaults', 'declineDefaults', 'help', 'openConfig', 'exitStudio', 'codexLogin', 'codexStatus', 'codexCatalog', 'codexPing', 'codexLogout', 'stop', 'cancelTrace'}:
            self._values(command.get('values', {}), extra)
        callbacks = {'save': app.save, 'start': app.start_server, 'stop': app.stop_server,
                     'health': app._delayed_health_check, 'validate': app.validate_paths,
                     'trace': app.refresh_trace, 'codexLogin': app.codex_login,
                     'codexStatus': app.codex_status, 'codexCatalog': app.refresh_codex_text_catalog,
                     'codexPing': app.ping_codex_image_account, 'clearLora': app.clear_lora_settings,
                     'useLora': app.use_selected_lora, 'resetSprite': app.reset_sprite_resize,
                     'openCache': app.open_cache_folder, 'cancelTrace': app.cancel_trace_refresh,
                     'codexLogout': app.codex_logout}
        if action in {'acceptDefaults', 'declineDefaults'}:
            from infini_local.desktop.settings_defaults import decide_defaults
            changed = decide_defaults(CONFIG_PATH, extra.get('revision'), accept=action == 'acceptDefaults')
            # No collect/save or whole-profile baseline capture: unrelated native
            # and browser drafts remain unsaved, including the selected preset.
            guard = app.__dict__.get('_profile_edit_guard', False)
            app._profile_edit_guard = True
            try:
                for key, value in changed.items():
                    app.data[key] = value
                    if key in app.vars:
                        app.vars[key].set(value)
                    elif key in app.text_widgets:
                        widget = app.text_widgets[key]
                        self._write_text(widget, value)
                    elif key in app.__dict__.get('_profile_extra_settings', {}):
                        app._profile_extra_settings[key] = value
            finally:
                app._profile_edit_guard = guard
            app.status_var.set('Рекомендованные изменения записаны в config.env.' if changed else
                               'Рекомендации отклонены. config.env не изменён.')
        elif action in callbacks:
            return callbacks[action]()
        elif action == 'clearTrace':
            return app.clear_trace_files(confirmed=True)
        elif action == 'forceRestart':
            if extra.get('confirm') is not True:
                raise ValueError('Explicit confirmation is required to interrupt active generation')
            return app._request_server_action(restart=True, force=True)
        elif action == 'applyPreset':
            app.preset_var.set(str(extra.get('name', CUSTOM_PRESET)))
            app.apply_preset()
        elif action == 'savePreset':
            name = str(extra.get('name', '')).strip()
            app.user_presets = save_user_preset(CONFIG_PATH.with_name('gui_user_presets.json'), name, app._current_profile_settings())
            app.preset_var.set(USER_PRESET_PREFIX + name)
            app._capture_profile_baseline()
            app.status_var.set(f'Профиль «{name}» сохранён. config.env не изменён.')
        elif action == 'browse':
            raise ValueError('Выбери путь в браузерном списке файлов или введи его вручную.')
        elif action == 'help':
            from infini_local.desktop.settings_gui_theme import ROOT
            if not (ROOT.parent / 'START_HERE.html').is_file():
                raise ValueError('Локальная инструкция не найдена.')
            return {'ok': True, 'message': 'Локальная инструкция готова.', 'result': {
                'kind': 'guide', 'title': 'Локальная инструкция',
                'url': '/guide?token=' + self.server.token + '#/docs/user/START_RU.md'}}
        elif action == 'openConfig':
            path = CONFIG_PATH
            if not path.is_file():
                raise ValueError('Файл ещё не существует. Сначала явно сохрани конфигурацию.')
            with path.open('r', encoding='utf-8') as stream:
                content = stream.read(262145)
            if len(content) > 262144:
                raise ValueError('Файл слишком большой для просмотра в Studio.')
            # Read-only preview is not a credential reveal control.
            def mask_setting(match):
                key = match.group(1).strip()
                secret = re.search(r'(?:^|_)(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIALS?)(?:_|$)', key, re.I)
                return key + '=••••••••' if secret and match.group(2).strip() else match.group(0)
            content = re.sub(r'^[\t \ufeff]*([^#=\r\n]+?)[\t ]*=[\t ]*(.*)$', mask_setting, content, flags=re.M)
            return {'ok': True, 'message': 'Файл открыт для просмотра.', 'result': {
                'kind': 'document', 'title': 'Сохранённый config.env',
                'path': str(path), 'content': content}}
        elif action == 'exitStudio':
            with self.server._lock:
                self.server.accepting_actions = False
            app.on_close()

    def tick(self):
        if self.app._gui_closed:
            return
        for _ in range(8):
            try:
                command = self.server.commands.get_nowait()
            except queue.Empty:
                break
            if self.app._gui_closed:
                break
            try:
                self.apply(command)
            except (OSError, ValueError, AttributeError, RuntimeError, tk.TclError) as exc:
                self.app.status_var.set(f'Не удалось выполнить действие: {exc}')
                # apply() already retained a terminal receipt for this command.
                pass
        if not self.app._gui_closed:
            self.server.publish(self.snapshot())
            self.app.after(150, self.tick)
        else:
            # Closing destroys Tk state; publish the final receipt from the last
            # immutable snapshot instead of touching dead widgets.
            with self.server._lock:
                final_state = copy.deepcopy(self.server._state)
            final_state.update(lastAction=self.last_action, actionResults=list(self.action_results.values()), closed=True)
            self.server.publish(final_state)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Open the local Infinicraft Studio.')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args(argv)
    from infini_local.desktop.settings_gui import SettingsGui
    try:
        app = SettingsGui()
    except (ValueError, UnicodeError) as exc:
        raise SystemExit(f'Не удалось прочитать config.env: {exc} '
                         'Исправь указанную строку в редакторе или восстанови резервную копию, затем открой Studio снова.') from None
    app.withdraw()
    server = StudioServer(Path(__file__).with_name('webui'), port=args.port)
    controller = StudioController(app, server)
    server.publish(controller.snapshot())
    server.start()
    # Token URL is needed once to attach the user's browser; do not write it to log files.
    print('Infinicraft Studio: ' + server.url, flush=True)
    print('Close this console to exit Studio. The generator has its own Stop control.', flush=True)
    if not args.no_browser:
        webbrowser.open(server.url)
    app.after(0, controller.tick)
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.on_close()
    finally:
        # Let polling clients observe the terminal close receipt before the
        # loopback listener disappears. No Tk callbacks run after destruction.
        if server._state.get('closed'):
            time.sleep(5)
        server.close()


if __name__ == '__main__':
    main()
