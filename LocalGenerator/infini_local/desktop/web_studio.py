from __future__ import annotations

"""Loopback-only browser Studio and main-thread adapter for the desktop controller.

HTTP workers exchange immutable JSON snapshots and queued commands only. Existing
safe restart, profile, OAuth and trace owners stay on the Tk main thread.
"""

import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import secrets
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser

from infini_local.desktop.tk_compat import tk

ACTIONS = frozenset({
    'save', 'start', 'stop', 'health', 'validate', 'trace', 'applyPreset', 'savePreset',
    'codexLogin', 'codexStatus', 'codexCatalog', 'codexPing', 'clearLora', 'useLora',
    'resetSprite', 'openConfig', 'openCache', 'clearTrace', 'browse', 'help', 'exitStudio',
    'forceRestart', 'cancelTrace', 'codexLogout',
})
STATIC_FILES = {'/studio.css': ('studio.css', 'text/css; charset=utf-8'),
                '/studio.js': ('studio.js', 'text/javascript; charset=utf-8')}


class StudioServer:
    def __init__(self, assets: Path, *, port: int = 0):
        self.assets = assets
        self.token = secrets.token_urlsafe(32)
        self.commands: queue.Queue[dict] = queue.Queue(maxsize=32)
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
                if path == '/api/state':
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
                    owner.commands.put_nowait({'id': identifier, 'action': action, 'values': values, 'extra': extra})
                    self.reply(202, {'ok': True, 'id': identifier})
                except queue.Full:
                    self.reply(429, {'error': 'Studio is busy; retry after the current operation'})
                except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
                    self.reply(400, {'error': 'Invalid action request'})

        self.httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.httpd.daemon_threads = True
        self.base_url = f'http://127.0.0.1:{self.httpd.server_port}'
        self.url = self.base_url + '/?token=' + self.token

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
        from infini_local.desktop.settings_schema import DEFAULTS, PRESETS
        from infini_local.desktop.settings_env import parse_env
        from infini_local.desktop.settings_gui_theme import EXAMPLE_PATH
        from infini_local.desktop.settings_gui_trace_state import CONFIG_PATH
        values = self.app._current_profile_settings()
        values['INFINI_GUI_PIPELINE_PRESET'] = self.app.preset_var.get()
        # Controller values include unsaved edits from non-saving actions. A fresh
        # browser must compare them to disk, never adopt them as a saved baseline.
        saved_error = ''
        try:
            # Match SettingsGui startup: a fresh install loads the example.
            saved_values = parse_env(CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH)
            self._saved_values = dict(saved_values)
        except OSError as exc:
            # A transient read failure must not kill polling or certify a draft.
            saved_values = dict(self._saved_values or DEFAULTS)
            saved_error = f'Не удалось проверить сохранённую конфигурацию: {exc}'
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
        return {
            'values': values, 'savedValues': saved_values, 'savedLanEnabled': saved_lan,
            'defaults': DEFAULTS, 'fields': fields, 'presets': PRESETS,
            'userPresets': self.app.user_presets, 'status': saved_error or self.app.status_var.get(),
            'activity': self.app.activity_var.get(), 'appliedConfig': self.app.applied_config_var.get(),
            'home': {'state': self.app.home_state_var.get(), 'detail': self.app.home_detail_var.get(),
                     'config': self.app.home_config_var.get()},
            'trace': {key: widget.get('1.0', 'end-1c') for key, widget in self.app.trace_texts.items()},
            'configPath': str(CONFIG_PATH), 'version': '0.4.254', 'lastAction': self.last_action,
            'revision': self.revision, 'busy': list(self.app._gui_tasks), 'lanEnabled': bool(self.app.radmin_enabled.get()),
            'account': {'catalog': self.app.codex_catalog_var.get(), 'images': self.app.codex_image_account_var.get()},
        }

    def _values(self, values, extra):
        for key, value in values.items():
            if key in self.app.vars:
                if self.app.vars[key].get() != value:
                    self.app.vars[key].set(value)
            elif key in self.app.text_widgets:
                widget = self.app.text_widgets[key]
                if widget.get('1.0', 'end-1c') != value:
                    widget.delete('1.0', 'end')
                    widget.insert('1.0', value)
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

    def apply(self, command):
        from infini_local.desktop.settings_env import CUSTOM_PRESET, USER_PRESET_PREFIX, save_user_preset
        from infini_local.desktop.settings_gui_trace_state import CONFIG_PATH
        app = self.app
        action, extra = command['action'], command.get('extra', {})
        self._values(command.get('values', {}), extra)
        callbacks = {'save': app.save, 'start': app.start_server, 'stop': app.stop_server,
                     'health': app._delayed_health_check, 'validate': app.validate_paths,
                     'trace': app.refresh_trace, 'codexLogin': app.codex_login,
                     'codexStatus': app.codex_status, 'codexCatalog': app.refresh_codex_text_catalog,
                     'codexPing': app.ping_codex_image_account, 'clearLora': app.clear_lora_settings,
                     'useLora': app.use_selected_lora, 'resetSprite': app.reset_sprite_resize,
                     'openConfig': app.open_config, 'openCache': app.open_cache_folder,
                     'clearTrace': app.clear_trace_files, 'cancelTrace': app.cancel_trace_refresh,
                     'codexLogout': app.codex_logout}
        if action in callbacks:
            callbacks[action]()
        elif action == 'forceRestart':
            if extra.get('confirm') is not True:
                raise ValueError('Explicit confirmation is required to interrupt active generation')
            app._request_server_action(restart=True, force=True)
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
            key, kind = str(extra.get('key', '')), str(extra.get('type', 'file'))
            if key not in app.vars:
                raise ValueError('Unknown path field')
            if kind == 'folder':
                app.browse_folder(key)
            elif kind == 'model':
                app.browse_model(key)
            elif kind == 'lora':
                app.browse_lora_file()
            else:
                app.browse_file(key)
        elif action == 'help':
            app.status_var.set('Запуск: выбери текстовую модель и изображения, сохрани настройки, затем запусти сервер. Подробная инструкция: docs/user/START_RU.md.')
        elif action == 'exitStudio':
            app.on_close()
        self.revision += 1
        self.last_action = {'id': command['id'], 'action': action, 'ok': True, 'revision': self.revision}

    def tick(self):
        if self.app._gui_closed:
            return
        for _ in range(8):
            try:
                command = self.server.commands.get_nowait()
            except queue.Empty:
                break
            try:
                self.apply(command)
            except (OSError, ValueError, AttributeError, RuntimeError, tk.TclError) as exc:
                self.app.status_var.set(f'Не удалось выполнить действие: {exc}')
                self.last_action = {'id': command['id'], 'action': command['action'], 'ok': False, 'message': str(exc)}
        if not self.app._gui_closed:
            self.server.publish(self.snapshot())
            self.app.after(150, self.tick)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Open the local Infinicraft Studio.')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args(argv)
    from infini_local.desktop.settings_gui import SettingsGui
    app = SettingsGui()
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
        server.close()


if __name__ == '__main__':
    main()
