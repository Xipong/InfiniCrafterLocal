"""Headless Studio worker operations, server guards, OAuth and diagnostics.

All public state is plain data; only the owner loop applies worker results.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import threading
from queue import Empty, Queue
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import webbrowser
from pathlib import Path, PureWindowsPath

from infini_local.storage import trace_tools
from infini_local.core import http_io
from infini_local.services.sdcpp_backend import lora_dir_from_file
from infini_local.desktop.settings_paths import (
    ROOT,
)


from infini_local.desktop.settings_interactions import notify, finish_action, begin_action, saved_config_revision


class StudioOperations:
    def _run_gui_task(self, name, work, on_result):
        """Worker -> queue -> owner event loop; workers receive only captured plain data."""
        if self.__dict__.get("_gui_closed", False):
            return
        tasks = self.__dict__.setdefault("_gui_tasks", {})
        previous = tasks.get(name)
        if previous:
            previous["cancel"].set()
            # Coalesce refresh clicks: one bounded in-flight worker and one
            # newest captured request, never one thread per click.
            if previous["pending"] is not None:
                finish_action(self, previous["pending"][2], False, "Запрос заменён более новым.", cancelled=True)
            previous["pending"] = (work, on_result, self.__dict__.get("_studio_command_id"))
            return
        state = {"cancel": threading.Event(), "results": Queue(maxsize=1), "after": None, "pending": None,
                 "command_id": self.__dict__.get("_studio_command_id")}
        tasks[name] = state

        def worker():
            try:
                state["results"].put((True, work(state["cancel"])))
            except Exception:
                # Raw transport errors can include credentials/URLs. UI gets only
                # a failure flag; a workflow may return its own safe diagnostics.
                state["results"].put((False, None))

        def poll():
            if self.__dict__.get("_gui_closed", False) or tasks.get(name) is not state:
                return
            try:
                result = state["results"].get_nowait()
            except Empty:
                state["after"] = self.after(100, poll)
                return
            tasks.pop(name, None)
            if state["pending"] is not None:
                finish_action(self, state["command_id"], False, "Запрос заменён более новым.", cancelled=True)
                work_next, apply_next, identifier = state["pending"]
                previous_id = self.__dict__.get("_studio_command_id")
                self._studio_command_id = identifier
                try:
                    self._run_gui_task(name, work_next, apply_next)
                finally:
                    self._studio_command_id = previous_id
            elif not state["cancel"].is_set():
                previous_notice_id = self.__dict__.get("_studio_notification_action_id")
                self._studio_notification_action_id = state["command_id"]
                try:
                    outcome = on_result(*result)
                    if isinstance(outcome, dict):
                        finish_action(self, state["command_id"], outcome.get("ok", result[0]), outcome.get("message", ""),
                                      saved=outcome.get("saved", False))
                    else:
                        finish_action(self, state["command_id"], result[0], "Действие завершено." if result[0] else "Действие не выполнено.")
                except Exception:
                    # Transport and subprocess exceptions may contain secrets.
                    finish_action(self, state["command_id"], False, "Не удалось завершить действие. Проверь настройки и журнал.")
                    self.status = ("Не удалось завершить действие. Проверь настройки и журнал.")
                finally:
                    self._studio_notification_action_id = previous_notice_id
            else:
                finish_action(self, state["command_id"], False, "Действие отменено.", cancelled=True)

        threading.Thread(target=worker, daemon=True, name="settings-" + name).start()
        state["after"] = self.after(100, poll)

    def _cancel_gui_task(self, name):
        state = self.__dict__.get("_gui_tasks", {}).get(name)
        if state:
            state["cancel"].set()
            if state["pending"] is not None:
                finish_action(self, state["pending"][2], False, "Действие отменено.", cancelled=True)
            state["pending"] = None
            # Keep polling solely to reap the bounded in-flight worker. A new
            # refresh coalesces until its network timeout/result returns.

    def ping_codex_image_account(self):
        """Read-only connectivity probe, with one bounded in-flight worker."""
        from infini_local.services import codex_catalog

        begin_action(self)
        self.codex_image_account = "Проверка аккаунта через read-only текстовый endpoint…"
        self.status = "Codex: проверка аккаунта; image-доступ не проверяется."

        def work(cancel):
            codex_catalog.list_text_models()

        def apply(ok, result):
            self.codex_image_account = (
                "Аккаунт доступен через текстовый каталог; image-доступ не проверен (нет image-каталога)."
                if ok else "Аккаунт/сеть не ответили; image-доступ не проверен. Выбранная image-модель сохранена.")
            self.status = self.codex_image_account
            return {"ok": ok, "message": self.codex_image_account}

        self._run_gui_task("codex-image-ping", work, apply)

    def refresh_codex_text_catalog(self):
        """Account catalog; only the owner loop publishes worker results."""
        from infini_local.services import codex_catalog

        begin_action(self)
        self.codex_catalog = "Читаем текстовые модели текущего Codex-аккаунта…"

        def work(cancel):
            return codex_catalog.list_text_models()

        def apply(ok, models):
            if ok:
                self._codex_text_models = {model.slug: model for model in models}
                current = self.values["INFINI_CODEX_LLM_MODEL"].strip()
                choices = [model.slug for model in models]
                if current and current not in choices:
                    choices.insert(0, current)
                self.codex_models = choices
                self.codex_catalog = f"Текстовый каталог аккаунта: {len(models)} моделей. Список не проверяет image-доступ."
            else:
                self.codex_catalog = "Не удалось обновить текстовый каталог. Сохранённый slug остаётся; проверь вход/сеть."
            self.status = self.codex_catalog
            return {"ok": ok, "message": self.codex_catalog}

        self._run_gui_task("codex-catalog", work, apply)

    def codex_login(self):
        from queue import Queue
        from infini_local.services import codex_auth
        if getattr(self, "_codex_login_running", False):
            self.status = ("Codex OAuth: вход уже ожидает завершения в браузере.")
            return {"ok": False, "message": self.status}
        self._codex_login_command_id = begin_action(self)
        self._codex_login_running = True
        self._codex_login_cancel = threading.Event()
        self._codex_login_results = Queue()
        cancel, results = self._codex_login_cancel, self._codex_login_results
        self.status = ("Codex OAuth: заверши вход в открывшемся браузере (3 минуты).")
        def worker():
            try:
                codex_auth.login(cancel=cancel)
                results.put((True, "Codex OAuth: вход выполнен. Выбери openai_codex и сохрани настройки."))
            except codex_auth.CodexError as exc:
                results.put((False, str(exc)))
            except Exception:
                results.put((False, "Codex OAuth: не удалось открыть браузер или сохранить сессию."))
        threading.Thread(target=worker, daemon=True, name="codex-oauth-login").start()
        self.after(150, self._poll_codex_login)

    def _poll_codex_login(self):
        from queue import Empty
        try:
            result = self._codex_login_results.get_nowait()
        except Empty:
            self.after(150, self._poll_codex_login)
            return
        self._codex_login_running = False
        ok, message = result
        self.status = (message)
        self._codex_account_status = message
        finish_action(self, self.__dict__.get('_codex_login_command_id'), ok, message)

    def codex_status(self):
        from infini_local.services.codex_auth import auth_status
        status = auth_status()
        text = "вход не выполнен"
        if status["authenticated"]:
            text = "сессия сохранена; токен обновится при запросе" if status["expired"] else "сессия готова"
        self.status = ("Codex OAuth: " + text + ". Квота проверяется сервером при генерации.")
        self._codex_account_status = self.status
        return {"ok": True, "message": self.status}

    def codex_logout(self):
        from infini_local.services.codex_auth import logout
        if getattr(self, "_codex_login_running", False):
            self._codex_login_cancel.set()
            self.status = ("Codex OAuth: отмена входа; после завершения нажми Sign out ещё раз.")
            return {"ok": False, "message": self.status}
        try:
            logout()
            # A worker may have fetched the previous account's catalog before
            # sign-out. Retire every queued UI result and remove account metadata.
            self._cancel_gui_task("codex-catalog")
            self._cancel_gui_task("codex-image-ping")
            self._codex_text_models = {}
            current = self.values["INFINI_CODEX_LLM_MODEL"].strip()
            self.codex_models = list([current] if current else [])
            self.codex_catalog = ("Сессия удалена; каталог очищен. Сохранённый slug не проверен.")
            self.codex_image_account = ("Сессия удалена; image-доступ не проверен.")
            self.status = ("Codex OAuth: локальная сессия InfiniCrafter удалена.")
            self._codex_account_status = self.status
            return {"ok": True, "message": self.status}
        except OSError:
            self.status = ("Codex OAuth: не удалось удалить локальную сессию.")
            return {"ok": False, "message": self.status}


    def _server_base_url(self) -> str:
        data = self.collect()
        host = data.get("INFINI_HOST") or "127.0.0.1"
        if host == "0.0.0.0":
            host = "127.0.0.1"
        port = data.get("INFINI_PORT") or "5055"
        return f"http://{host}:{port}"

    def _saved_or_owned_server_base_url(self):
        if self.proc is not None and self.proc.poll() is None:
            owned = self.__dict__.get('_owned_server_base_url')
            if owned:
                return owned
        from infini_local.desktop.settings_env import parse_env
        values = parse_env(self.config_path if self.config_path.exists() else self.example_path)
        host = values.get('INFINI_HOST') or '127.0.0.1'
        if host == '0.0.0.0':
            host = '127.0.0.1'
        return f"http://{host}:{values.get('INFINI_PORT') or '5055'}"

    @staticmethod
    def _norm_path_for_compare(value: str | Path) -> str:
        # Preserve POSIX case while comparing Windows drive/UNC names under
        # Linux tests too. Never turn a distinct case-sensitive copy into ours.
        text = str(value or "").strip()
        if os.name == "nt" or PureWindowsPath(text).drive:
            return PureWindowsPath(text).as_posix().rstrip("/").casefold()
        return str(Path(text)).rstrip("/")


    def _health_matches_this_gui(self, snap: dict) -> bool:
        # Custom cache roots make cache-derived server-root guesses unsafe.
        # Require the explicit runtime acknowledgement for remote operations.
        root = str(snap.get("serverRoot") or "").strip()
        if not root:
            return False
        return self._norm_path_for_compare(root) == self._norm_path_for_compare(ROOT)


    @staticmethod
    def _read_gui_json(url: str, timeout: float, max_bytes: int | None = 16 * 1024 * 1024, *, method: str = "GET") -> dict:
        # Reuse the transport-owned monotonic/redirect/body boundary. A trickled
        # body must not retain a GUI task forever through idle-timeout resets.
        deadline = time.monotonic() + timeout
        # Windows system proxies need not bypass loopback. Local helper control
        # must reach the helper directly; provider/LAN requests retain proxies.
        loopback = urlsplit(url).hostname in {"127.0.0.1", "localhost", "::1"}
        with http_io.urlopen_no_redirect(urllib.request.Request(url, method=method, data=b"{}" if method == "POST" else None,
                headers={"Content-Type": "application/json"} if method == "POST" else {}), deadline=deadline, use_proxy=not loopback) as response:
            body = http_io.read_with_deadline(response, deadline=deadline, max_bytes=max_bytes)
        value = json.loads(body.decode("utf-8", "replace"))
        if not isinstance(value, dict):
            raise ValueError("GUI diagnostic endpoint returned no object")
        return value

    def _fetch_health_snapshot(self, timeout: float = 8, base_url: str | None = None) -> dict:
        base_url = base_url if base_url is not None else self._server_base_url()
        return self._read_gui_json(base_url + "/health", timeout=timeout)


    def _try_http_shutdown_current_server(self, timeout: float = 2.0, base_url: str | None = None, force: bool = False) -> tuple[bool, str]:
        base_url = base_url if base_url is not None else self._server_base_url()
        url = base_url + ("/shutdown?force=1" if force else "/shutdown")
        try:
            reply = self._read_gui_json(url, timeout=timeout, max_bytes=64 * 1024, method="POST")
            if reply.get("ok") is True:
                return True, ""
            return False, "Shutdown refused or not acknowledged."
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                return False, "Safe restart refused: generator busy (atomic server guard)."
            return False, "Shutdown refused by server; no process termination attempted."
        except Exception:
            return False, "Shutdown unavailable; no process termination attempted."

    def _wait_until_helper_stops(self, timeout: float = 4.0, base_url: str | None = None, cancel: threading.Event | None = None) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                return False
            try:
                # Windows may take about two seconds to report WSAECONNREFUSED;
                # use the remaining bounded stop budget, not a sub-second probe.
                self._fetch_health_snapshot(timeout=max(0.05, deadline - time.monotonic()), base_url=base_url)
            except Exception as exc:
                # Closing an HTTP listener can reset an in-flight connection
                # before the next connect reports refusal. Use the remaining
                # bounded budget; only refusal proves the port is free. A reset,
                # timeout, 503 or malformed response is never success by itself.
                if self._connection_was_refused(exc):
                    return True
            if cancel is not None:
                cancel.wait(min(0.2, max(0, deadline - time.monotonic())))
            else:
                time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        return False


    def validate_paths(self):
        data = self.collect()
        warnings = []
        backend = data.get("INFINI_IMAGE_BACKEND", "")
        if backend == "sdcpp" and data.get("INFINI_SDCPP_SERVER_AUTOSTART") == "1":
            exe = data.get("INFINI_SDCPP_SERVER_EXE", "")
            rocm_root = data.get("INFINI_SDCPP_ROCM_COMPAT_ROOT", "")
            model = data.get("INFINI_SDCPP_MODEL", "")
            vae = data.get("INFINI_SDCPP_VAE", "")
            llm = data.get("INFINI_SDCPP_LLM", "")
            lora_file = data.get("INFINI_SDCPP_LORA_FILE", "")
            lora_dir = lora_dir_from_file(lora_file)
            if exe and not Path(exe).exists():
                warnings.append(f"sd-server.exe не найден: {exe}")
            if rocm_root and not Path(rocm_root).is_dir():
                warnings.append(f"ROCm hybrid runtime не найден: {rocm_root}")
            if model and not Path(model).exists():
                warnings.append(f"Diffusion model не найден: {model}")
            if vae and not Path(vae).exists():
                warnings.append(f"VAE/AE не найден: {vae}")
            if llm and not Path(llm).exists():
                warnings.append(f"Qwen/LLM не найден: {llm}")
            if lora_file and not Path(lora_file).exists():
                warnings.append(f"LoRA file не найден: {lora_file}")
            if lora_file and lora_dir and not Path(lora_dir).exists():
                warnings.append(f"Папка LoRA, выведенная из файла, не найдена: {lora_dir}")
            if data.get("INFINI_SDCPP_LORA_PROMPT_TAGS", "").strip() and not lora_dir:
                warnings.append("LoRA prompt tags заполнены, но LoRA file не выбран — GUI не может вывести --lora-model-dir.")
            if not vae:
                warnings.append("VAE/AE пустой: для FLUX.2 Klein и Z-Image обычно нужен ae.safetensors.")
            if not llm:
                warnings.append("Qwen/LLM пустой: для FLUX.2 Klein и Z-Image обычно нужен Qwen3 *.gguf.")
        if data.get("INFINI_LLM_PROVIDER") == "openrouter" and not data.get("INFINI_OPENROUTER_API_KEY"):
            warnings.append("OpenRouter выбран, но API key пустой.")
        for slot in (2, 3, 4):
            prefix = f"INFINI_LLM_POOL_{slot}_"
            if data.get(prefix + "ENABLED") != "1":
                continue
            provider = (data.get(prefix + "PROVIDER") or "openai_compat").strip().lower()
            if not (data.get(prefix + "MODEL") or "").strip():
                warnings.append(f"LLM {slot} включён, но Model пустой — profile не попадёт в round-robin pool.")
            if provider == "openrouter" and not (data.get(prefix + "API_KEY") or "").strip():
                warnings.append(f"LLM {slot}: OpenRouter выбран, но API key пустой.")
        if backend == "openai_codex":
            from infini_local.services.codex_auth import auth_status
            if not auth_status()["authenticated"]:
                warnings.append("Codex OAuth выбран, но вход не выполнен. Нажми Sign in with ChatGPT.")
        if backend == "image_api" and not data.get("INFINI_IMAGE_API_KEY"):
            warnings.append("Image API выбран, но API key пустой.")
        asset_transport = (data.get("INFINI_MP_ASSET_TRANSPORT") or "native").strip().lower()
        if self.lan_enabled and asset_transport == "http":
            url = data.get("INFINI_ASSET_PUBLIC_BASE_URL", "")
            if not url or "26.x.x.x" in url:
                warnings.append("Radmin/LAN включён, но Public asset URL не заполнен реальным Radmin IP: http://26.xxx.xxx.xxx:5055")
            if data.get("INFINI_HOST") != "0.0.0.0":
                warnings.append("Radmin/LAN включён, но Host не 0.0.0.0 — друзья не достучатся до LocalGenerator asset host.")
        if warnings:
            notify(self, "warning", "Проверка настроек", "\n".join(warnings))
            self.status = ("Есть предупреждения по настройкам.")
            return {"ok": False, "message": "\n".join(warnings)}
        else:
            notify(self, "info", "Проверка настроек", "Критичных проблем в настройках не вижу.")
            self.status = ("Проверка прошла без критичных предупреждений.")
            return {"ok": True, "message": "Проверка прошла без критичных предупреждений."}

    def _shutdown_identity_is_safe(self, snap: dict) -> bool:
        if not isinstance(snap, dict) or snap.get("ok") is not True:
            return False
        pid = snap.get("pid")
        return (
            self._health_matches_this_gui(snap)
            and type(pid) is int and pid > 0 and pid != os.getpid()
        )

    @staticmethod
    def _activity_restart_refusal(snap: dict) -> str:
        activity = snap.get("generationActivity")
        if not isinstance(activity, dict):
            return "Safe restart refused: generation activity unknown."
        active, waiting, accepting = (activity.get(key) for key in ("active", "waiting", "accepting"))
        if type(active) is not int or active < 0 or type(waiting) is not int or waiting < 0 or type(accepting) is not bool:
            return "Safe restart refused: generation activity unknown."
        if active or waiting:
            return f"Safe restart refused: generator busy (active={active}, waiting={waiting}). Wait, or explicitly Force restart."
        if not accepting:
            return "Safe restart refused: server is not accepting generation; shutdown already in progress."
        return ""

    def start_server(self):
        return self._request_server_action(restart=True)


    @staticmethod
    def _connection_was_refused(exc: Exception) -> bool:
        reason = getattr(exc, "reason", exc)
        return isinstance(reason, ConnectionRefusedError) or getattr(reason, "errno", None) in {111, 61, 10061}

    def _request_server_action(self, restart: bool, force: bool = False):
        if "server-action" in self.__dict__.get("_gui_tasks", {}):
            self.status = ("Server action already in progress; wait for its result.")
            return {"ok": False, "message": "Действие сервера уже выполняется."}
        expected_revision = self.__dict__.get("_studio_expected_config_revision")
        owned_running = self.proc is not None and self.proc.poll() is None
        owned_url = self.__dict__.get('_owned_server_base_url') if owned_running else None
        base_url = owned_url or (self._server_base_url() if restart else self._saved_or_owned_server_base_url())
        data = self.collect() if restart else None
        self.status = ("Force restart: checking identity…" if force else "Safe restart/stop: checking generation activity…")
        shutdown_acknowledged = threading.Event()

        def work(cancel):
            try:
                # A two-second Windows connect deadline can expire just before
                # the closed-port refusal, misclassifying a free port as unknown.
                snap = self._fetch_health_snapshot(timeout=5, base_url=base_url)
            except Exception as exc:
                if restart and not owned_running and self._connection_was_refused(exc):
                    return ""
                return "Restart/stop refused: health/activity unknown; no process termination attempted."
            if not self._shutdown_identity_is_safe(snap):
                return "Restart refused: unknown/foreign server root or unsafe PID. GUI не будет убивать чужой процесс."
            refusal = "" if force else self._activity_restart_refusal(snap)
            if refusal or cancel.is_set():
                return refusal or "Restart cancelled."
            if self._safe_effective_config(snap) is None:
                return "Restart/stop refused: applied-config projection unverified; no shutdown or process termination attempted."
            stopped, refusal = self._try_http_shutdown_current_server(timeout=2, base_url=base_url, force=force)
            if not stopped:
                return refusal
            shutdown_acknowledged.set()
            if not self._wait_until_helper_stops(timeout=4, base_url=base_url, cancel=cancel):
                if restart:
                    return "Restart refused: shutdown acknowledged, but the port is not confirmed free; no new server launched. Check connection before retrying."
                return "Stop unconfirmed: shutdown acknowledged, but completion was not confirmed. Check connection before retrying."
            return ""

        def apply(ok, refusal):
            if shutdown_acknowledged.is_set():
                # Once shutdown was accepted, an earlier health response cannot
                # keep certifying readiness even if closure remains unconfirmed.
                self._cancel_gui_task("health-config")
                self._applied_config_ack = None
                self._server_lifecycle = "unknown"
                self.applied_config = ("Runtime config unconfirmed: shutdown was requested; check connection.")
            if not ok or refusal:
                self.status = (refusal if ok else "Safe restart refused: activity unknown.")
                return {"ok": False, "message": self.status}
            if expected_revision is not None and expected_revision != saved_config_revision(self.config_path, example_path=self.example_path):
                self.status = ("Запуск отменён: сохранённая конфигурация изменилась во время проверки. Проверь значения и запусти снова.")
                return {"ok": False, "message": self.status}
            if restart and self.collect() != data:
                self.status = ("Restart cancelled: GUI settings changed while checking; start again.")
                return {"ok": False, "message": self.status}
            if restart:
                return self._start_server_after_guard()
            else:
                self.proc = None
                self._server_lifecycle = "stopped"
                self.__dict__.pop('_owned_launch_settings', None)
                self.__dict__.pop('_owned_server_base_url', None)
                self._cancel_gui_task("health-config")
                self._applied_config_ack = None
                scheduled = self.__dict__.get("_health_after_id")
                if scheduled is not None:
                    self.after_cancel(scheduled)
                    self._health_after_id = None
                self._update_applied_config_feedback("Stopped")
                self.status = ("Server stopped through guarded /shutdown.")
                return {"ok": True, "message": self.status}

        self._run_gui_task("server-action", work, apply)

    def _start_server_after_guard(self):
        # Only the acknowledged shutdown/free-port path reaches launch. Never
        # terminate/kill a PID here: that would bypass atomic busy admission.
        self._cancel_gui_task("health-config")
        self._applied_config_ack = None
        self._update_applied_config_feedback()
        self.save()
        launch_values = self.collect()
        launch_url = self._server_base_url()
        env = os.environ.copy()
        env.update(launch_values)
        cmd = [sys.executable, str(ROOT / "server.py")]
        try:
            options = {"cwd": str(ROOT), "env": env}
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            self.proc = subprocess.Popen(cmd, **options)
            self._owned_launch_settings = dict(launch_values)
            self._owned_server_base_url = launch_url
            self._server_lifecycle = "starting"
            self.status = ("server.py запущен. Runtime config ещё не подтверждён.")
            previous = self.__dict__.get("_health_after_id")
            if previous is not None:
                self.after_cancel(previous)
            def check_launched_server():
                self._health_after_id = None
                self._delayed_health_check()
            self._health_after_id = self.after(1000, check_launched_server)
            return {"ok": True, "message": self.status, "saved": True}
        except Exception:
            self._server_lifecycle = "unknown"
            message = "Настройки сохранены в config.env, но не удалось запустить server.py; проверь Python/права/порт. Runtime config не подтверждён."
            notify(self, "error", "Не удалось запустить сервер", message)
            self.status = (message)
            # Saving and launching are separate outcomes. The failed launch must
            # still acknowledge this command's persisted baseline to its tab.
            return {"ok": False, "message": message, "saved": True}

    @staticmethod
    def _safe_effective_config(snap: dict) -> dict | None:
        # Exact parent-agreed partial projection, not a copy of loaded config.
        effective = snap.get("effectiveConfig")
        if not isinstance(effective, dict):
            return None
        types: dict[str, type] = {key: str for key in (
            "cacheDir", "worldRecipesDir", "imageBackend", "llmProvider", "llmModel", "openrouterProvider",
        )}
        types["sdcppAutostart"] = bool
        # A running server from before the language setting remains restartable;
        # its missing language is unconfirmed, never a claimed default.
        if "language" in effective:
            types["language"] = str
        if any(type(effective.get(key)) is not kind for key, kind in types.items()):
            return None
        return {key: effective[key] for key in types}

    def _proposed_effective_config(self) -> dict:
        # This is a partial comparison of launch inputs, not a second runtime
        # config owner. No token/key/URL/freeform command fields are projected.
        env = os.environ.copy()
        env.update(self.collect())
        cache = self._cache_dir_from_environment(env)
        worlds = Path(env.get("INFINI_WORLD_RECIPES_DIR", str(cache / "world_recipes")).strip())
        worlds = (worlds if worlds.is_absolute() else ROOT / worlds).resolve()
        provider = env.get("INFINI_LLM_PROVIDER", "").strip().lower().replace("-", "_")
        # Read-only comparison normalization from llm_transport's main-profile
        # rules; never import runtime bootstrap (which creates cache folders).
        if provider in {"openrouter", "or"}:
            provider = "openrouter"
        elif provider in {"openai", "openai_compat", "api", "remote"}:
            provider = "openai_compat"
        elif provider in {"local", "lmstudio", "lm_studio", "ollama", ""}:
            or_model = next((env[key].strip() for key in ("INFINI_OPENROUTER_MODEL", "OPENROUTER_MODEL") if env.get(key, "").strip()), "auto")
            # Only the legacy implicit provider decision observes configured
            # credential presence; no credential/value/hash is projected or kept.
            implicit_or = not provider and any(env.get(key, "").strip() for key in ("INFINI_OPENROUTER_API_KEY", "OPENROUTER_API_KEY")) and or_model.lower() not in {"auto", "default"}
            provider = "openrouter" if implicit_or else "local"
        backend = env.get("INFINI_IMAGE_BACKEND", "sdcpp").strip().lower()
        # These declared canonical aliases are parity-tested against the visual
        # owner; this is display comparison only, never backend dispatch/config.
        backend = {
            "stablediffusioncpp": "sdcpp", "stable-diffusion.cpp": "sdcpp", "stable_diffusion_cpp": "sdcpp",
            "api_image": "image_api", "openai_image": "image_api", "openai_images": "image_api",
            "openai_compat_image": "image_api", "none": "off", "disabled": "off",
        }.get(backend, backend)
        model_keys = {
            "local": ("INFINI_LMSTUDIO_MODEL", "OPENAI_MODEL"),
            "openrouter": ("INFINI_OPENROUTER_MODEL", "OPENROUTER_MODEL"),
            "openai_compat": ("INFINI_OPENAI_COMPAT_MODEL", "OPENAI_MODEL"),
            "openai_codex": ("INFINI_CODEX_LLM_MODEL",),
        }.get(provider, ())
        # Match core.llm_config env_first and the primary auth snapshot: auto is
        # config-only, never resolved through a catalog/provider request here.
        model = next((env[key].strip() for key in model_keys if env.get(key, "").strip()),
                     "" if provider == "openai_codex" else "auto")
        return {
            "cacheDir": str(cache), "worldRecipesDir": str(worlds),
            "language": env.get("INFINI_LANGUAGE", "ru").strip().lower(),
            "imageBackend": backend,
            "llmProvider": provider,
            "llmModel": model,
            "openrouterProvider": env.get("INFINI_OPENROUTER_PROVIDER", "").strip() if provider == "openrouter" else "",
            "sdcppAutostart": env.get("INFINI_SDCPP_SERVER_AUTOSTART", "0").strip().lower() in {"1", "true", "yes", "on", "y", "t"},
        }


    def _update_applied_config_feedback(self, state: str = ""):
        prefix = state + "; " if state else ""
        ack = self.__dict__.get("_applied_config_ack")
        if not ack or ack.get("baseUrl") != self._server_base_url():
            self.applied_config = (prefix + "Runtime config unconfirmed (partial non-secret projection; pools/secrets unverified).")
            return
        proposed = self._proposed_effective_config()
        mismatches = [key for key in proposed if proposed[key] != ack["effectiveConfig"].get(key)]
        if mismatches:
            text = "Restart required / runtime mismatch: " + ", ".join(mismatches) + ". Partial non-secret projection; pools/secrets unverified."
        else:
            text = "Runtime matches launch settings at last health check (partial non-secret projection; pools/secrets unverified)."
        self.applied_config = (prefix + text)

    @staticmethod
    def _generation_activity_text(activity) -> str:
        """Read only the bounded health projection; these IDs are not native jobs."""
        if not isinstance(activity, dict):
            return "Backend activity unknown (last health snapshot)."
        active, waiting, accepting = (activity.get(key) for key in ("active", "waiting", "accepting"))
        if type(active) is not int or active < 0 or type(waiting) is not int or waiting < 0 or type(accepting) is not bool:
            return "Backend activity unknown (last health snapshot)."
        lines = [f"Backend last health snapshot: active={active}, waiting={waiting}, accepting={accepting}"]
        rows = activity.get("requests")
        if not isinstance(rows, list):
            return lines[0] + "\nRequest rows unknown."

        def seconds(value):
            return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 10**9

        def symbol(value):
            return isinstance(value, str) and re.fullmatch(r"[a-z0-9_]{1,80}", value) is not None

        for row in rows[:32]:
            if not isinstance(row, dict):
                lines.append("Request row unavailable.")
                continue
            request = row.get("requestId")
            stage, wait = row.get("stage"), row.get("waitReason")
            elapsed, stage_elapsed = row.get("elapsedSeconds"), row.get("stageElapsedSeconds")
            network = row.get("networkStarted")
            if (not isinstance(request, str) or re.fullmatch(r"[0-9a-f]{32}", request) is None
                    or (stage is not None and not symbol(stage)) or not symbol(wait)
                    or not all(seconds(value) for value in (elapsed, stage_elapsed))
                    or (network is not None and type(network) is not bool)):
                lines.append("Request row unavailable.")
                continue
            stage = stage if stage is not None else "unknown"
            profile = row.get("profileId")
            profile = profile if profile in ("llm_1", "llm_2", "llm_3") else "unknown"
            network_text = "unknown" if network is None else "started" if network else "not started"
            lines.append(f"{request} | profile={profile} | stage={stage} | elapsed={elapsed:g}s | stage elapsed={stage_elapsed:g}s | wait={wait} | network={network_text}")
        omitted = activity.get("requestsOmitted")
        omitted = omitted if type(omitted) is int and omitted >= 0 else 0
        omitted += max(0, len(rows) - 32)
        if omitted:
            lines.append(f"{omitted} rows omitted")
        return "\n".join(lines)

    def _delayed_health_check(self):
        # Called by the owner loop, never a background thread. Capture plain launch
        # inputs here and return results through the same bounded queue pattern.
        if self.__dict__.get("_gui_closed", False):
            return
        studio_request = bool(self.__dict__.get("_studio_command_id"))
        base_url = self._saved_or_owned_server_base_url() if studio_request else self._server_base_url()
        expected_pid = self.proc.pid if self.proc is not None and self.proc.poll() is None else None
        self.applied_config = ("Checking runtime config (partial non-secret projection)…")

        def work(cancel):
            snap = self._fetch_health_snapshot(timeout=3, base_url=base_url)
            if not self._shutdown_identity_is_safe(snap) or (expected_pid is not None and snap.get("pid") != expected_pid):
                return None
            # Drop all other health/config/auth metadata before it enters the UI
            # queue or cached acknowledgement; unexpected fields cannot leak.
            safe = self._safe_effective_config(snap)
            if safe is None:
                return None
            return {"pid": snap.get("pid"), "baseUrl": base_url, "effectiveConfig": safe,
                    "activityText": self._generation_activity_text(snap.get("generationActivity"))}

        def apply(ok, ack):
            current_target = self._saved_or_owned_server_base_url() if studio_request else self._server_base_url()
            if ack is not None and ack["baseUrl"] != current_target:
                ack = None
            self.activity = ack["activityText"] if ok and ack is not None else "Backend activity unknown (health unavailable or foreign server)."
            if not ok or ack is None:
                self._applied_config_ack = None
                self._server_lifecycle = "unknown"
                self.applied_config = ("Runtime config unconfirmed: health/projection unavailable or другая копия (partial; secrets/pools unverified).")
                return {"ok": False, "message": self.applied_config}
            self._applied_config_ack = ack
            self._server_lifecycle = "responding"
            self._update_applied_config_feedback()
            self.status = (self.applied_config)
            return {"ok": True, "message": self.applied_config}

        self._run_gui_task("health-config", work, apply)

    def stop_server(self):
        return self._request_server_action(restart=False)

    def on_close(self):
        if self.__dict__.get("_gui_closed", False):
            return
        self._gui_closed = True
        # Retire every receipt before removing callbacks; shutdown of Studio is
        # independent from the owned generator process and never terminates it.
        identifiers = set(self.__dict__.get("_studio_async_ids", set()))
        for state in self.__dict__.get("_gui_tasks", {}).values():
            state["cancel"].set()
            identifiers.add(state["command_id"])
            if state["pending"] is not None:
                identifiers.add(state["pending"][2])
            state["pending"] = None
        identifiers.add(self.__dict__.get("_codex_login_command_id"))
        for identifier in identifiers - {None}:
            finish_action(self, identifier, False, "Студия закрыта; действие отменено.", cancelled=True)
        self.__dict__.get("_gui_tasks", {}).clear()
        self._health_after_id = None
        if getattr(self, "_codex_login_running", False):
            self._codex_login_cancel.set()
        self.cancel_scheduled()

    @staticmethod
    def _cache_dir_from_environment(env: dict[str, str]) -> Path:
        # Match env_path() and the GUI launch cwd, including an explicit blank
        # override (Path("") == cwd). Do not expand ~ or reinterpret saved keys.
        cache = Path(env.get("INFINI_CACHE_DIR", str(ROOT / "cache")).strip())
        return (cache if cache.is_absolute() else ROOT / cache).resolve()

    def _effective_cache_dir(self) -> Path:
        env = os.environ.copy()
        env.update(self.collect())
        return self._cache_dir_from_environment(env)

    def _load_local_trace_snapshot(self, reason: str = "", cache: Path | None = None) -> dict:
        cache = cache if cache is not None else self._effective_cache_dir()
        return {
            "ok": False,
            "source": "local_cache_fallback",
            "version": "server unavailable",
            "serverRoot": str(ROOT),
            "cacheDir": str(cache),
            "pipeline": {"note": "server.py не ответил или отвечает другая копия; показан локальный cache", "reason": reason},
            "traceConfig": {"eventsFile": str(cache / "events.ndjson"), "promptTraceFile": str(cache / "prompt_trace.ndjson"), "pipelineTraceFile": str(cache / "pipeline_trace.ndjson")},
            "events": trace_tools.tail_ndjson(cache / "events.ndjson", 120),
            "promptTrace": trace_tools.tail_ndjson(cache / "prompt_trace.ndjson", 120),
            "pipelineTrace": trace_tools.tail_ndjson(cache / "pipeline_trace.ndjson", 120),
            "sdcpp": {
                "logFile": str(cache / "sdcpp_server.log"),
                "logTail": trace_tools.tail_text_file(cache / "sdcpp_server.log", 20000),
            },
            "lastCombineFailure": json.loads((cache / "last_combine_failure.json").read_text(encoding="utf-8")) if (cache / "last_combine_failure.json").exists() else None,
        }

    def _fetch_trace_snapshot(self, base_url: str | None = None) -> dict:
        base_url = base_url if base_url is not None else self._server_base_url()
        health = self._fetch_health_snapshot(timeout=8, base_url=base_url)
        if not self._health_matches_this_gui(health):
            raise RuntimeError("Trace refused: другая копия server.py")
        snap = self._read_gui_json(base_url + "/trace.json", timeout=18, max_bytes=None)
        if not self._health_matches_this_gui(snap) or snap.get("pid") != health.get("pid"):
            raise RuntimeError("Trace refused: server identity changed")
        return snap

    def _pretty(self, value) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return str(value)

    def _fmt_event_line(self, ev: dict, include_prompts: bool = False) -> str:
        ts = ev.get("ts") or ev.get("createdAt") or ""
        stage = ev.get("stage") or ev.get("level") or ev.get("kind") or "event"
        title = ev.get("title") or ev.get("message") or ""
        head = f"[{ts}] {stage} :: {title}\n"
        payload = {k: v for k, v in ev.items() if k not in {"prompt", "negative", "response"}}
        body = self._pretty(payload)
        if include_prompts:
            if ev.get("prompt"):
                body += "\n\n--- PROMPT ---\n" + str(ev.get("prompt"))
            if ev.get("negative"):
                body += "\n\n--- NEGATIVE ---\n" + str(ev.get("negative"))
            if ev.get("response"):
                body += "\n\n--- RESPONSE ---\n" + str(ev.get("response"))
        return head + body + "\n" + ("═" * 96) + "\n"

    def refresh_trace(self, *, base_url=None, cache=None):
        # Capture plain settings on the owner thread before starting any I/O.
        base_url = self._server_base_url() if base_url is None else base_url
        cache = self._effective_cache_dir() if cache is None else cache
        self.trace_status = ("Loading trace…")

        def work(cancel):
            try:
                snap = self._fetch_trace_snapshot(base_url=base_url)
                return snap, "Trace loaded from server /trace.json"
            except Exception:
                if cancel.is_set():
                    return None
                reason = "server unavailable or identity mismatch"
                snap = self._load_local_trace_snapshot(reason, cache=cache)
                return snap, f"Local cache fallback: {cache} ({reason})"

        def apply(ok, result):
            if not ok or result is None:
                self.trace_status = ("Trace unavailable; local trace could not be read.")
                return {"ok": False, "message": self.trace_status}
            snap, status = result
            self.trace_status = (status)
            self._render_trace_snapshot(snap)
            return {"ok": True, "message": status}

        self._run_gui_task("trace", work, apply)

    def cancel_trace_refresh(self):
        self._cancel_gui_task("trace")
        self.trace_status = ("Trace refresh cancelled; any in-flight read is being retired.")

    def _render_trace_snapshot(self, snap: dict):
        pipeline = snap.get("pipeline") or {}
        trace_cfg = snap.get("traceConfig") or {}
        summary = []
        summary.append("INFICRAFTER TRACE SUMMARY")
        summary.append("═" * 96)
        summary.append(f"version: {snap.get('version')}")
        summary.append(f"cache:   {snap.get('cacheDir')}")
        summary.append("")
        summary.append("PIPELINE")
        summary.append(self._pretty(pipeline))
        summary.append("")
        summary.append("TRACE FILES")
        summary.append(self._pretty(trace_cfg))
        self._set_trace_text("summary", "\n".join(summary))

        prompt_events = snap.get("promptTrace") or []
        self._set_trace_text("prompts", "".join(self._fmt_event_line(ev, include_prompts=True) for ev in reversed(prompt_events)) or "Пока prompt trace пуст.")
        pipe_events = snap.get("pipelineTrace") or []
        self._set_trace_text("pipeline", "".join(self._fmt_event_line(ev) for ev in reversed(pipe_events)) or "Пока pipeline trace пуст.")
        events = snap.get("events") or []
        self._set_trace_text("events", "".join(self._fmt_event_line(ev) for ev in reversed(events)) or "Пока events пуст.")
        self._set_trace_text("sdcpp", self._pretty(snap.get("sdcpp") or {}))
        self._set_trace_text("failure", self._pretty(snap.get("lastCombineFailure")))


    def open_cache_folder(self):
        cache = self._effective_cache_dir()
        cache.mkdir(parents=True, exist_ok=True)
        os.startfile(cache) if os.name == "nt" else webbrowser.open(cache.as_uri())
        self.status = (f"Opened launch cache: {cache}")

    def clear_trace_files(self, *, confirmed=False):
        if "trace-clear" in self.__dict__.get("_gui_tasks", {}):
            self.trace_status = ("Trace clear already in progress.")
            return {"ok": False, "message": "Очистка журнала уже выполняется."}
        if not confirmed:
            return {"ok": False, "message": "Trace clear requires confirmation."}
        base_url = self._server_base_url()
        cache = self._effective_cache_dir()
        self._cancel_gui_task("trace")
        self.trace_status = ("Clearing trace…")

        def work(cancel):
            try:
                health = self._fetch_health_snapshot(timeout=2, base_url=base_url)
            except Exception as exc:
                # HTTP refusals/timeouts are not proof that the selected helper
                # is offline; never truncate its files as a destructive fallback.
                if not self._connection_was_refused(exc):
                    return "Trace clear refused: server liveness/identity unavailable."
                health = None
            if cancel.is_set():
                return None
            if health is not None:
                if health.get("ok") is not True or not self._health_matches_this_gui(health):
                    return "Trace clear refused: unknown/foreign server root."
                projection = health.get("effectiveConfig") or {}
                live_cache = projection.get("cacheDir") if isinstance(projection, dict) else None
                live_cache = live_cache or health.get("cacheDir")
                if not isinstance(live_cache, str) or self._norm_path_for_compare(live_cache) != self._norm_path_for_compare(cache):
                    return "Trace clear refused: live cache differs from launch cache or is unverified. Check applied config / restart."
                reply = self._read_gui_json(base_url + "/trace_clear", timeout=4, max_bytes=64 * 1024, method="POST")
                cleared = reply.get("cleared")
                expected = {self._norm_path_for_compare(cache / name) for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson")}
                acknowledged = set()
                if isinstance(cleared, list):
                    for value in cleared:
                        if isinstance(value, str):
                            path = Path(value)
                            path = (path if path.is_absolute() else ROOT / path).resolve()
                            acknowledged.add(self._norm_path_for_compare(path))
                if reply.get("ok") is not True or not expected.issubset(acknowledged):
                    return "Trace clear unavailable; server did not confirm all selected trace files."
                return "Trace cleared through this server."
            paths = [cache / name for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson")]
            # Refuse known linked trace/lock leaves before clearing any file;
            # folder configuration never authorizes mutation of their targets.
            if any(path.is_symlink() or path.with_name(path.name + ".lock").is_symlink() for path in paths):
                return "Trace clear refused: linked trace/lock file outside the selected-file contract."
            for path in paths:
                if cancel.is_set():
                    return None
                trace_tools.clear_ndjson(path)
            return f"Trace cleared locally: {cache}"

        def apply(ok, result):
            self.trace_status = (result if ok and result else "Trace clear unavailable; not confirmed.")
            if ok and result and result.startswith("Trace cleared"):
                self.refresh_trace(base_url=base_url, cache=cache)
            return {"ok": bool(ok and result and result.startswith("Trace cleared")), "message": result or "Trace clear unavailable; not confirmed."}

        self._run_gui_task("trace-clear", work, apply)


    def _set_trace_text(self, key: str, content: str):
        self.trace[key] = content

    def force_restart_server(self, *, confirmed=False):
        if not confirmed:
            return {"ok": False, "message": "Force restart requires confirmation."}
        return self._request_server_action(restart=True, force=True)
