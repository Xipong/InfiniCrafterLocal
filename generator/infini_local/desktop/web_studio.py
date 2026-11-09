from __future__ import annotations

"""Loopback-only HTTP transport and serialized commands for the browser Studio."""

import argparse
import copy
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import re
import secrets
import stat
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

from infini_local.desktop.settings_interactions import saved_config_revision
from infini_local.core import strict_json

ACTION_BODY_TIMEOUT_SECONDS = 10

ACTIONS = frozenset({
    'save', 'start', 'stop', 'health', 'validate', 'trace', 'applyPreset', 'savePreset',
    'codexLogin', 'codexStatus', 'codexCatalog', 'codexPing', 'clearLora', 'useLora',
    'resetSprite', 'openConfig', 'openConfigFolder', 'openCache', 'clearTrace', 'browse', 'help', 'exitStudio',
    'forceRestart', 'cancelTrace', 'codexLogout', 'acceptDefaults', 'declineDefaults', 'onboardingProgress', 'sdCatalog', 'sdInstall', 'sdCancel',
})
STATIC_FILES = {'/studio.css': ('studio.css', 'text/css; charset=utf-8'),
                '/studio.js': ('studio.js', 'text/javascript; charset=utf-8'),
                '/studio-i18n.js': ('studio-i18n.js', 'text/javascript; charset=utf-8'),
                '/studio-onboarding.js': ('studio-onboarding.js', 'text/javascript; charset=utf-8'),
                '/studio-onboarding.css': ('studio-onboarding.css', 'text/css; charset=utf-8'),
                '/studio-motion.js': ('studio-motion.js', 'text/javascript; charset=utf-8')}


class StudioServer:
    def __init__(self, assets: Path, *, port: int = 0):
        self.assets = assets
        self.token = secrets.token_urlsafe(32)
        from infini_local.core.app_paths import ROOT, STATE_ROOT
        self.file_root = STATE_ROOT
        self.guide_path = ROOT.parent / 'START_HERE.html'
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
                return secrets.compare_digest(supplied.encode('utf-8'), owner.token.encode('utf-8'))

            def do_GET(self):
                path = urlsplit(self.path).path
                if path == '/guide':
                    if not (self.authorized() or self.authorized(bootstrap=True)):
                        self.reply(403, {'error': 'Session access required'})
                        return
                    try:
                        guide = owner.guide_path.read_bytes()
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
                    lengths = self.headers.get_all('Content-Length', [])
                    if self.headers.get('Transfer-Encoding') is not None or len(lengths) != 1:
                        raise ValueError('Unsupported request framing')
                    length = lengths[0].strip()
                    if not length.isascii() or not length.isdecimal():
                        raise ValueError('Invalid Content-Length')
                    size = int(length)
                    if not 0 < size <= 2 * 1024 * 1024:
                        self.reply(413, {'error': 'Request size limit exceeded'})
                        return
                    previous_timeout = self.connection.gettimeout()
                    deadline = time.monotonic() + ACTION_BODY_TIMEOUT_SECONDS
                    body = bytearray()
                    try:
                        while len(body) < size:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                raise TimeoutError('Action body deadline exceeded')
                            self.connection.settimeout(remaining)
                            chunk = self.rfile.read1(size - len(body))
                            if not chunk:
                                raise ValueError('Incomplete action body')
                            body.extend(chunk)
                    finally:
                        self.connection.settimeout(previous_timeout)
                    payload = strict_json.loads_object(body)
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
                except TimeoutError:
                    self.reply(408, {'error': 'Action request timed out'})
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
        installer = getattr(self, 'sdcpp_installer', None)
        if installer is not None:
            installer.close()
        if self._thread is not None:
            self.httpd.shutdown()
            self._thread.join(timeout=3)
        self.httpd.server_close()


class StudioController:
    """Apply browser commands on the Python control loop and publish JSON state."""
    def __init__(self, app, server: StudioServer):
        self.app, self.server = app, server
        self.fields = self._fields()
        self._saved_values: dict | None = None
        self._projections = {}
        from infini_local.desktop.studio_sdcpp_install import SdcppInstaller
        self.installer = SdcppInstaller(app.config_path)
        if server is not None:
            server.sdcpp_installer = self.installer

    def _fields(self):
        from infini_local.desktop.settings_fields import FIELDS
        return copy.deepcopy(FIELDS)

    @staticmethod
    def _file_witness(path):
        try:
            info = path.stat()
            return (str(path.resolve()), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        except FileNotFoundError:
            return (str(path), None)

    def _cached(self, name, witness, build):
        cached = self._projections.get(name)
        if cached is None or cached[0] != witness:
            value = build()
            self._projections[name] = (witness, value)
            return value
        return cached[1]

    def _saved_projection(self, witness):
        path, example = self.app.config_path, self.app.example_path
        values = self.app.read_saved_settings()
        revision = saved_config_revision(path, example_path=example)
        source = path if path.exists() else example
        if witness != (path.exists(), self._file_witness(source)):
            raise OSError('Конфигурация изменилась во время чтения; повторяем проверку.')
        return values, revision

    def snapshot(self):
        from itertools import islice
        from infini_local import APP_VERSION
        from infini_local.desktop.settings_schema import DEFAULTS, FIELD_HELP, PRESETS
        from infini_local.desktop.settings_defaults import defaults_offer
        from infini_local.desktop.studio_onboarding import load_progress
        CONFIG_PATH, EXAMPLE_PATH = self.app.config_path, self.app.example_path
        from infini_local.services.codex_auth import auth_status
        from infini_local.services.codex_text_backend import EFFORTS
        from infini_local.desktop.windows_folder_picker import is_available
        values = self.app._current_profile_settings()
        values['INFINI_GUI_PIPELINE_PRESET'] = self.app.preset
        # Controller values include unsaved edits from non-saving actions. A fresh
        # browser must compare them to disk, never adopt them as a saved baseline.
        saved_error = ''
        saved_revision = None
        try:
            # Match SettingsGui startup: a fresh install loads the example.
            source = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH
            witness = (CONFIG_PATH.exists(), self._file_witness(source))
            # Recheck at every save admission; this cache is display-only.
            saved_values, saved_revision = self._cached('saved', witness, lambda: self._saved_projection(witness))
            saved_values = dict(saved_values)
            self._saved_values = dict(saved_values)
        except (OSError, ValueError, UnicodeError) as exc:
            # A transient read failure must not kill polling or certify a draft.
            saved_values = dict(self._saved_values or DEFAULTS)
            saved_error = f'Не удалось проверить сохранённую конфигурацию: {exc}'
        try:
            defaults_update = self._cached('defaults', (self._file_witness(CONFIG_PATH), self._file_witness(CONFIG_PATH.with_name(CONFIG_PATH.name + '.defaults.json'))), lambda: defaults_offer(CONFIG_PATH))
        except (OSError, UnicodeError, ValueError) as exc:
            # A recommendation read must not take the entire control plane down.
            defaults_update = {'changes': [], 'dismissed': True}
            saved_error = saved_error or f'Не удалось проверить рекомендации: {exc}'
        saved_values['INFINI_GUI_PIPELINE_PRESET'] = self.app._pipeline_preset_from_config(saved_values, self.app.user_presets)
        saved_lan = saved_values.get('INFINI_HOST') == '0.0.0.0' or bool(saved_values.get('INFINI_ASSET_PUBLIC_BASE_URL'))
        fields = self._cached('fields', (tuple(self.app.field_disabled_reasons.items()), tuple(self.app.codex_models)), lambda: [dict(field, disabled=self.app.field_disabled_reasons.get(field['key'], ''), **({'options': list(self.app.codex_models)} if field['key'] == 'INFINI_CODEX_LLM_MODEL' else {})) for field in self.fields])
        # Keep generic reasoning choices in the shared snapshot. Each browser
        # selects Codex catalog efforts for its own unsaved provider/model draft.
        # The catalog owner already validates/redacts model IDs. Publish only
        # bounded text-model metadata, so each tab can describe its own draft
        # selection without mutating the shared controller or querying providers.
        models = tuple(islice(self.app.__dict__.get('_codex_text_models', {}).values(), 256))
        text_models = self._cached('models', models, lambda: {
            model.slug: {'efforts': [effort for effort in model.efforts if effort in EFFORTS],
                         'defaultEffort': model.default_effort if model.default_effort in EFFORTS else ''}
            for model in models
        })
        self.app.observe_runtime_notifications()
        self.app.refresh_home()
        return {
            'values': values, 'savedValues': saved_values, 'savedLanEnabled': saved_lan, 'savedRevision': saved_revision,
            'defaults': DEFAULTS, 'fieldHelp': FIELD_HELP, 'defaultsUpdate': defaults_update,
            'onboarding': load_progress(CONFIG_PATH), 'sdcppInstall': self.installer.snapshot(),
            'fields': fields, 'presets': PRESETS,
            'inactiveSettings': ['INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED', 'INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD'],
            'userPresets': self.app.user_presets, 'status': saved_error or self.app.status,
            'activity': self.app.activity, 'appliedConfig': self.app.applied_config,
            'runtime': self.app.runtime_status(),
            'home': {'code': self.app.home_code, 'state': self.app.home_state, 'detail': self.app.home_detail,
                     'config': self.app.home_config},
            'traceStatus': self.app.trace_status,
            'notifications': self.app.actions.notifications, 'actionResults': list(self.app.actions.results.values()),
            'trace': dict(self.app.trace),
            'configPath': str(CONFIG_PATH.absolute()), 'version': APP_VERSION, 'lastAction': self.app.actions.last_action,
            'managed': bool(self.app.__dict__.get('_managed_by_tmodloader', False)),
            'nativeFolderPicker': is_available(),
            'revision': self.app.actions.revision, 'busy': list(self.app.actions.tasks), 'lanEnabled': bool(self.app.lan_enabled),
            'account': {'status': self.app.__dict__.get('_codex_account_status', ''), 'catalog': self.app.codex_catalog,
                        'images': self.app.codex_image_account, 'authenticated': auth_status()['authenticated'],
                        'textModels': text_models},
        }

    def _values(self, values, extra):
        self.app.update_values(values, lan_enabled=extra.get('lanEnabled'))

    def apply(self, command):
        previous_action = self.app.actions.last_action
        identifier = self.app.actions.start(command)
        try:
            outcome = self._apply(command)
            pending = identifier in self.app.actions.pending_ids
            if not pending:
                outcome = outcome if isinstance(outcome, dict) else {}
                self.app.actions.finish(identifier, outcome.get('ok', True), outcome.get('message', self.app.status if not self.app._gui_closed else 'Студия закрыта.'),
                                    result=outcome.get('result'), saved=outcome.get('saved', False),
                                    values=outcome.get('values'), lan_enabled=outcome.get('lanEnabled'))
        except (OSError, ValueError, AttributeError, RuntimeError) as exc:
            self.app.actions.finish(identifier, False, str(exc))
            raise
        finally:
            # Help progress must not hide a failed generator action on the dashboard.
            if command['action'] in {'onboardingProgress', 'sdCatalog', 'sdInstall', 'sdCancel'}:
                self.app.actions.last_action = previous_action
            self.app.actions.command_id = None
            self.app.actions.expected_config_revision = None

    def _apply(self, command):
        from infini_local.desktop.settings_env import CUSTOM_PRESET, USER_PRESET_PREFIX, save_user_preset
        CONFIG_PATH = self.app.config_path
        app = self.app
        action, extra = command['action'], command.get('extra', {})
        if action == 'onboardingProgress':
            from infini_local.desktop.studio_onboarding import save_progress
            progress = save_progress(CONFIG_PATH, extra)
            return {'message': '', 'result': {'kind': 'onboarding', 'progress': progress}}
        if action in {'sdCatalog', 'sdInstall', 'sdCancel'}:
            expected = {'buildId'} if action == 'sdInstall' else set()
            if set(extra) != expected:
                raise ValueError('Unexpected installer arguments')
            if action == 'sdInstall':
                result = self.installer.install(extra['buildId'])
            else:
                result = (self.installer.refresh_catalog if action == 'sdCatalog' else self.installer.cancel)()
            return {'message': '', 'result': {'kind': 'sdcppInstall', 'state': result}}
        if action == 'forceRestart' and extra.get('confirm') is not True:
            raise ValueError('Explicit confirmation is required to interrupt active generation')
        if action in {'start', 'forceRestart'} and 'server-action' in app.actions.tasks:
            # Refuse before adopting another tab's draft: the in-flight guard
            # still compares and launches from the shared control-loop state.
            return (app.start_server() if action == 'start' else
                    app.force_restart_server(confirmed=extra.get('confirm') is True))
        if action in {'save', 'start', 'forceRestart'} and 'savedRevision' in extra:
            if not extra['savedRevision'] or extra['savedRevision'] != saved_config_revision(CONFIG_PATH, example_path=self.app.example_path):
                raise ValueError('Конфигурация на диске изменилась в другой вкладке или программе. Черновик сохранён в этой вкладке. Проверь новые сохранённые значения перед повторным сохранением или запуском.')
        if action in {'save', 'start', 'forceRestart'}:
            from infini_local.desktop.settings_env import parse_env
            from infini_local.desktop.settings_schema import DEFAULTS
            EXAMPLE_PATH = app.example_path
            # Retained extension keys may have been removed on disk since this
            # adapter loaded. Keep current disk keys and explicit draft edits,
            # but never resurrect an absent key from the adapter's stale cache.
            saved = parse_env(CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH)
            retained = set(DEFAULTS) | set(saved) | set(command.get('values', {}))
            for key in set(app.values) - retained:
                del app.values[key]
            # Extension values belong to the latest disk snapshot unless this
            # command explicitly edits them. Do not overwrite another program's
            # update using the controller's startup cache.
            for key, value in saved.items():
                if key not in DEFAULTS and key not in command.get('values', {}):
                    app.values[key] = value
        if action == 'clearTrace' and extra.get('confirm') is not True:
            raise ValueError('Подтверди очистку журнала в браузере.')
        if action in {'trace', 'clearTrace', 'openCache'}:
            from infini_local.core.server_endpoint import resolve_server_endpoint
            from infini_local.desktop.settings_env import parse_env
            owned = app.proc is not None and app.proc.poll() is None
            target = app.__dict__.get('_owned_launch_settings') if owned else None
            if target is None:
                target = parse_env(CONFIG_PATH if CONFIG_PATH.exists() else app.example_path)
            base_url = resolve_server_endpoint(target).base_url
            cache = app._cache_dir_from_environment({**os.environ, **target})
            if action == 'trace':
                return app.refresh_trace(base_url=base_url, cache=cache)
            if action == 'clearTrace':
                return app.clear_trace_files(confirmed=True, base_url=base_url, cache=cache)
            return app.open_cache_folder(cache=cache)
        if action in {'applyPreset', 'clearLora', 'useLora', 'resetSprite', 'savePreset', 'validate'}:
            draft = {**app.values, **command.get('values', {})}
            lan = extra.get('lanEnabled', app.lan_enabled)
            if action == 'validate':
                return app.validate_paths(data=app.collect(draft, preset=draft.get('INFINI_GUI_PIPELINE_PRESET', app.preset), lan_enabled=lan), lan_enabled=lan)
            if action == 'applyPreset':
                return app.apply_preset(draft, preset=str(extra.get('name', CUSTOM_PRESET)), lan_enabled=lan)
            if action == 'savePreset':
                name = str(extra.get('name', '')).strip()
                app.user_presets = save_user_preset(CONFIG_PATH.with_name('gui_user_presets.json'), name, draft, overwrite=extra.get('overwrite') is True)
                draft['INFINI_GUI_PIPELINE_PRESET'] = USER_PRESET_PREFIX + name
                app.status = f'Профиль «{name}» сохранён. config.env не изменён.'
                return {'values': draft, 'lanEnabled': lan}
            return {'clearLora': app.clear_lora_settings, 'useLora': app.use_selected_lora, 'resetSprite': app.reset_sprite_resize}[action](draft, lan_enabled=lan)
        if action in {'save', 'start', 'forceRestart'}:
            self._values(command.get('values', {}), extra)
        callbacks = {'save': app.save, 'start': app.start_server, 'stop': app.stop_server,
                     'health': app._delayed_health_check, 'codexLogin': app.codex_login,
                     'codexStatus': app.codex_status, 'codexCatalog': app.refresh_codex_text_catalog,
                     'codexPing': app.ping_codex_image_account,
                     'openConfigFolder': app.open_config_folder,
                     'cancelTrace': app.cancel_trace_refresh,
                     'codexLogout': app.codex_logout}
        if action in {'acceptDefaults', 'declineDefaults'}:
            from infini_local.desktop.settings_defaults import decide_defaults
            changed = decide_defaults(CONFIG_PATH, extra.get('revision'), accept=action == 'acceptDefaults')
            # Apply only the explicitly reviewed recommendation keys.
            app.values.update(changed)
            app._refresh_visibility()
            app.status = ('Рекомендованные изменения записаны в config.env.' if changed else
                          'Рекомендации отклонены. config.env не изменён.')
        elif action in callbacks:
            return callbacks[action]()
        elif action == 'forceRestart':
            return app.force_restart_server(confirmed=extra.get('confirm') is True)
        elif action == 'browse':
            from infini_local.desktop.windows_folder_picker import choose_folder, is_available
            key, path = extra.get('key'), extra.get('path', '')
            field = next((field for field in self.fields if field['key'] == key), None)
            if field is None or field.get('browse') != 'folder' or field.get('secret') or not isinstance(path, str):
                raise ValueError('Native folder selection requires a registered folder setting')
            if not is_available():
                raise ValueError('Системный выбор папки доступен только на Windows-компьютере генератора. Используй список Studio.')
            if 'native-folder-picker' in app.actions.tasks:
                raise ValueError('Окно выбора папки уже открыто на компьютере генератора.')
            # Existing local-path admission rejects UNC, mapped drives and links
            # before seeding the OS dialog, and validates the returned selection.
            initial = self.server.list_files(path, 'folder')['path']
            def work(cancel):
                if cancel.is_set():
                    return None
                selected = choose_folder(initial)
                if selected is None:
                    return None
                listing = self.server.list_files(selected, 'folder')
                if listing['warning'] or not Path(selected).is_dir():
                    raise ValueError('Selected folder is unavailable')
                return listing['path']
            def completed(ok, selected):
                if not ok:
                    return {'ok': False, 'message': 'Не удалось выбрать локальную папку. Используй список Studio или введи путь.'}
                if selected is None:
                    return {'ok': True, 'cancelled': True, 'message': 'Выбор папки отменён. Черновик не изменён.'}
                return {'ok': True, 'message': 'Папка выбрана. Изменён только черновик в этой вкладке.',
                        'result': {'kind': 'folderSelection', 'key': key, 'path': selected}}
            app.actions.run('native-folder-picker', work, completed)
        elif action == 'help':
            from infini_local.core.app_paths import ROOT
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
            except (OSError, ValueError, AttributeError, RuntimeError) as exc:
                self.app.status = f'Не удалось выполнить действие: {exc}'
                # apply() already retained a terminal receipt for this command.
                pass
        if not self.app._gui_closed:
            self.server.publish(self.snapshot())
            self.app.after(150, self.tick)
        else:
            # Publish final receipts without querying closed lifecycle state.
            with self.server._lock:
                final_state = copy.deepcopy(self.server._state)
            final_state.update(lastAction=self.app.actions.last_action, actionResults=list(self.app.actions.results.values()), closed=True)
            self.server.publish(final_state)


def _watch_parent(descriptor: int, shutdown: threading.Event) -> None:
    """Only the managed launcher uses stdin as a lifetime/control pipe."""
    pending = b''
    try:
        while not shutdown.is_set():
            chunk = os.read(descriptor, 1024)
            if not chunk:
                break
            pending += chunk
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                if line.strip().upper() == b'STOP':
                    shutdown.set()
                    return
            if len(pending) > 4096:
                break
    except OSError:
        pass
    shutdown.set()


def _stop_owned_generator(app) -> None:
    """Managed shutdown never adopts or terminates an external generator."""
    process = app.proc
    if process is None or process.poll() is not None:
        return
    url = app.__dict__.get('_owned_server_base_url')
    if url:
        try:
            health = app._fetch_health_snapshot(timeout=1, base_url=url)
            if health.get('pid') == process.pid and app._health_matches_this_gui(health):
                app._try_http_shutdown_current_server(timeout=1, base_url=url, force=True)
                process.wait(timeout=3)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def _validate_startup_assets(assets: Path):
    # READY means the browser can load the application, not merely an open socket.
    for name in ('index.html', *(entry[0] for entry in STATIC_FILES.values())):
        try:
            if not (assets / name).read_bytes():
                raise OSError('empty file')
        except OSError as exc:
            raise RuntimeError(f'Studio frontend is incomplete: {name}. '
                               'Restore the packaged runtime before opening Studio again.') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description='Open the local Infinicraft Studio.')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--managed', action='store_true', help='Stop when the owning tModLoader process closes stdin.')
    args = parser.parse_args(argv)
    from infini_local.desktop.settings_controller import SettingsController
    from infini_local.core.app_paths import CONFIG_PATH
    from infini_local.core.env_utils import load_env_file
    try:
        load_env_file(CONFIG_PATH)
        app = SettingsController()
    except (ValueError, UnicodeError) as exc:
        raise SystemExit(f'Не удалось прочитать config.env: {exc} '
                         'Исправь указанную строку в редакторе или восстанови резервную копию, затем открой Studio снова.') from None
    server = StudioServer(Path(__file__).with_name('webui'), port=args.port)
    app._managed_by_tmodloader = args.managed
    controller = StudioController(app, server)
    shutdown = threading.Event()
    try:
        _validate_startup_assets(server.assets)
        server.publish(controller.snapshot())
        app.after(0, controller.tick)
        app.pump()
        if app._gui_closed:
            raise RuntimeError('Studio closed during startup.')
        server.start()
        # The private URL goes only to the controlling pipe/user's console.
        if args.managed:
            threading.Thread(target=_watch_parent, args=(sys.stdin.fileno(), shutdown),
                             daemon=True, name='infini-studio-parent').start()
            print('IFC_STUDIO_READY ' + json.dumps({'url': server.url}), flush=True)
        else:
            print('Infinicraft Studio: ' + server.url, flush=True)
            print('Close this console to exit Studio. The generator has its own Stop control.', flush=True)
        if not args.no_browser:
            webbrowser.open(server.url)
        while not app._gui_closed and not shutdown.is_set():
            app.pump()
            shutdown.wait(0.02)
    except KeyboardInterrupt:
        app.on_close()
    finally:
        app.on_close()
        # Let polling clients observe the terminal close receipt before the
        # loopback listener disappears. Parent EOF interrupts this grace period
        # immediately, preserving the mod unload shutdown budget.
        if server._state.get('closed'):
            shutdown.wait(5)
        shutdown.set()
        server.close()
        if args.managed:
            _stop_owned_generator(app)


if __name__ == '__main__':
    main()
