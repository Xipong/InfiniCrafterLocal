"""Control-loop owner of Studio commands, bounded workers and browser receipts.

Settings owns this state. HTTP only submits commands and publishes snapshots;
there are no injected notification sinks or parallel pending-command registries.
"""
from collections import OrderedDict
from queue import Empty, Queue
import secrets
import threading


class StudioActions:
    def __init__(self, app):
        self.app = app
        self.command_id = None
        self.notification_id = None
        self.expected_config_revision = None
        self.pending_ids = set()
        self.tasks = {}
        self.results: OrderedDict[str, dict] = OrderedDict()
        self.last_action: dict = {}
        self.notifications: list[dict] = []
        self.revision = 0

    def start(self, command):
        identifier = command['id']
        self.results[identifier] = {'id': identifier, 'action': command['action'], 'ok': True,
                                    'status': 'running', 'message': 'Действие выполняется.'}
        self.last_action = self.results[identifier]
        self.command_id = identifier
        self.expected_config_revision = command.get('extra', {}).get('savedRevision')
        return identifier

    def mark_pending(self):
        if self.command_id:
            self.pending_ids.add(self.command_id)
        return self.command_id

    def close(self):
        for state in self.tasks.values():
            state['cancel'].set()
            state['pending'] = None
        for identifier in tuple(self.pending_ids):
            self.finish(identifier, False, 'Студия закрыта; действие отменено.', cancelled=True)
        self.tasks.clear()

    def notify(self, level, title, message):
        self.notifications.append({'id': secrets.token_hex(8), 'level': level, 'title': title, 'message': message,
                                   'actionId': self.notification_id or self.command_id})
        del self.notifications[:-64]

    def finish(self, identifier, ok, message, *, cancelled=False, result=None, saved=False, values=None, lan_enabled=None):
        self.pending_ids.discard(identifier)
        receipt = self.results.get(identifier)
        if receipt is None or receipt['status'] != 'running':
            return
        updates = dict(ok=bool(ok), status='cancelled' if cancelled else 'succeeded' if ok else 'failed',
                       message=message)
        if result is not None:
            updates['result'] = result
        if not self.app._gui_closed and receipt['action'] in {'applyPreset', 'clearLora', 'useLora', 'resetSprite', 'savePreset', 'save', 'start', 'forceRestart'}:
            updates['values'] = dict(values) if values is not None else self.app._current_profile_settings()
            if values is None:
                updates['values']['INFINI_GUI_PIPELINE_PRESET'] = self.app.preset
            updates['lanEnabled'] = bool(self.app.lan_enabled if lan_enabled is None else lan_enabled)
        if (ok or saved) and receipt['action'] in {'save', 'start', 'forceRestart', 'acceptDefaults'}:
            from infini_local.desktop.settings_env import parse_env
            CONFIG_PATH = self.app.config_path
            updates['savedValues'] = parse_env(CONFIG_PATH)
            updates['savedValues']['INFINI_GUI_PIPELINE_PRESET'] = self.app._pipeline_preset_from_config(updates['savedValues'], self.app.user_presets)
            updates['savedRevision'] = saved_config_revision(CONFIG_PATH, example_path=self.app.example_path)
            updates['saved'] = True
        self.revision += 1
        receipt.update(updates, revision=self.revision)
        self.last_action = receipt
        while len(self.results) > 128:
            retired = next((key for key, item in self.results.items() if item['status'] != 'running'), None)
            if retired is None:
                break
            del self.results[retired]

    def run(self, name, work, on_result):
        """Worker -> queue -> owner event loop; workers receive only captured plain data."""
        if self.app._gui_closed:
            return
        self.mark_pending()
        tasks = self.tasks
        previous = tasks.get(name)
        if previous:
            previous["cancel"].set()
            # Coalesce refresh clicks: one bounded in-flight worker and one
            # newest captured request, never one thread per click.
            if previous["pending"] is not None:
                self.finish(previous["pending"][2], False, "Запрос заменён более новым.", cancelled=True)
            previous["pending"] = (work, on_result, self.command_id)
            return
        state = {"cancel": threading.Event(), "results": Queue(maxsize=1), "pending": None,
                 "command_id": self.command_id}
        tasks[name] = state

        def worker():
            try:
                state["results"].put((True, work(state["cancel"])))
            except Exception:
                # Raw transport errors can include credentials/URLs. UI gets only
                # a failure flag; a workflow may return its own safe diagnostics.
                state["results"].put((False, None))

        def poll():
            if self.app._gui_closed or tasks.get(name) is not state:
                return
            try:
                result = state["results"].get_nowait()
            except Empty:
                self.app.after(100, poll)
                return
            tasks.pop(name, None)
            if state["pending"] is not None:
                self.finish(state["command_id"], False, "Запрос заменён более новым.", cancelled=True)
                work_next, apply_next, identifier = state["pending"]
                previous_id = self.command_id
                self.command_id = identifier
                try:
                    self.run(name, work_next, apply_next)
                finally:
                    self.command_id = previous_id
            elif not state["cancel"].is_set():
                previous_notice_id = self.notification_id
                self.notification_id = state["command_id"]
                try:
                    outcome = on_result(*result)
                    if isinstance(outcome, dict):
                        self.finish(state["command_id"], outcome.get("ok", result[0]), outcome.get("message", ""),
                                      saved=outcome.get("saved", False), cancelled=outcome.get("cancelled", False),
                                      result=outcome.get("result"))
                    else:
                        self.finish(state["command_id"], result[0], "Действие завершено." if result[0] else "Действие не выполнено.")
                except Exception:
                    # Transport and subprocess exceptions may contain secrets.
                    self.finish(state["command_id"], False, "Не удалось завершить действие. Проверь настройки и журнал.")
                    self.app.status = ("Не удалось завершить действие. Проверь настройки и журнал.")
                finally:
                    self.notification_id = previous_notice_id
            else:
                self.finish(state["command_id"], False, "Действие отменено.", cancelled=True)

        try:
            threading.Thread(target=worker, daemon=True, name="settings-" + name).start()
        except RuntimeError:
            # No worker exists to publish a result or retire this slot. This can
            # also happen when poll starts a coalesced successor, so keep the
            # control loop alive and allow a later command to retry.
            tasks.pop(name, None)
            message = "Не удалось запустить действие. Попробуй ещё раз."
            self.finish(state["command_id"], False, message)
            self.app.status = message
            return
        self.app.after(100, poll)

    def cancel(self, name):
        state = self.tasks.get(name)
        if state:
            state["cancel"].set()
            if state["pending"] is not None:
                self.finish(state["pending"][2], False, "Действие отменено.", cancelled=True)
            state["pending"] = None
            # Keep polling solely to reap the bounded in-flight worker. A new
            # refresh coalesces until its network timeout/result returns.


def saved_config_revision(config_path, *, example_path=None):
    """Fingerprint the exact saved source, including fresh-install provenance."""
    import hashlib
    from infini_local.core.app_paths import EXAMPLE_PATH
    existing = config_path.exists()
    path = config_path if existing else (EXAMPLE_PATH if example_path is None else example_path)
    return hashlib.sha256((b'config:' if existing else b'example:') + path.read_bytes()).hexdigest()
