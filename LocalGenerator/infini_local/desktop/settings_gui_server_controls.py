from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from queue import Empty, Queue
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path, PureWindowsPath

from infini_local.core import http_io
from infini_local.desktop.tk_compat import filedialog, messagebox
from infini_local.desktop.settings_gui_theme import (
    ROOT,
    CONFIG_PATH,
)


class SettingsGuiServerControlsMixin:
    def _run_gui_task(self, name, work, on_result):
        """Worker -> Queue -> Tk.after; workers receive only captured plain data."""
        if self.__dict__.get("_gui_closed", False):
            return
        tasks = self.__dict__.setdefault("_gui_tasks", {})
        previous = tasks.get(name)
        if previous:
            previous["cancel"].set()
            # Coalesce refresh clicks: one bounded in-flight worker and one
            # newest captured request, never one thread per click.
            previous["pending"] = (work, on_result)
            return
        state = {"cancel": threading.Event(), "results": Queue(maxsize=1), "after": None, "pending": None}
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
                self._run_gui_task(name, *state["pending"])
            elif not state["cancel"].is_set():
                on_result(*result)

        threading.Thread(target=worker, daemon=True, name="settings-" + name).start()
        state["after"] = self.after(100, poll)

    def _cancel_gui_task(self, name):
        state = self.__dict__.get("_gui_tasks", {}).get(name)
        if state:
            state["cancel"].set()
            state["pending"] = None
            # Keep polling solely to reap the bounded in-flight worker. A new
            # refresh coalesces until its network timeout/result returns.

    def ping_codex_image_account(self):
        """Read-only account connectivity probe; there is no image-model list API."""
        from infini_local.services import codex_catalog

        generation = getattr(self, "_codex_image_ping_generation", 0) + 1
        self._codex_image_ping_generation = generation
        results = Queue()
        self.codex_image_account_var.set("Проверка аккаунта через read-only текстовый endpoint…")
        self.status_var.set("Codex: проверка аккаунта; image-доступ не проверяется.")

        def worker():
            try:
                codex_catalog.list_text_models()
                results.put(True)
            except Exception:
                results.put(False)

        threading.Thread(target=worker, daemon=True, name="codex-image-account-ping").start()

        def poll():
            if generation != self._codex_image_ping_generation:
                return
            try:
                reachable = results.get_nowait()
            except Empty:
                self.after(150, poll)
                return
            self.codex_image_account_var.set(
                "Аккаунт доступен через текстовый каталог; image-доступ не проверен (нет image-каталога)."
                if reachable else "Аккаунт/сеть не ответили; image-доступ не проверен. Выбранная image-модель сохранена."
            )
            self.status_var.set(self.codex_image_account_var.get())

        self.after(150, poll)

    def refresh_codex_text_catalog(self):
        """Account-scoped read-only text catalog; only the Tk loop touches widgets."""
        from infini_local.services import codex_catalog

        generation = getattr(self, "_codex_catalog_generation", 0) + 1
        self._codex_catalog_generation = generation
        results = Queue()
        self.codex_catalog_var.set("Читаем текстовые модели текущего Codex-аккаунта…")

        def worker():
            try:
                results.put((True, codex_catalog.list_text_models()))
            except Exception:
                # Never display raw transport exceptions: they may include URLs or session data.
                results.put((False, ()))

        threading.Thread(target=worker, daemon=True, name="codex-text-catalog").start()

        def poll():
            if generation != self._codex_catalog_generation:
                return
            try:
                ok, models = results.get_nowait()
            except Empty:
                self.after(150, poll)
                return
            if ok:
                self._codex_text_models = {model.slug: model for model in models}
                current = self.vars["INFINI_CODEX_LLM_MODEL"].get().strip()
                choices = [model.slug for model in models]
                if current and current not in choices:
                    choices.insert(0, current)
                self.codex_model_combo.configure(values=choices)
                self.codex_catalog_var.set(f"Текстовый каталог аккаунта: {len(models)} моделей. Список не проверяет image-доступ.")
                self._update_codex_efforts()
            else:
                self.codex_catalog_var.set("Не удалось обновить текстовый каталог. Сохранённый slug остаётся; проверь вход/сеть.")
            self.status_var.set(self.codex_catalog_var.get())

        self.after(150, poll)

    def _update_codex_efforts(self):
        from infini_local.services.codex_text_backend import EFFORTS
        current = self.vars["INFINI_CODEX_LLM_MODEL"].get().strip()
        model = getattr(self, "_codex_text_models", {}).get(current)
        if model is None:
            if hasattr(self, "_codex_text_models") and current:
                self.codex_reasoning_combo.configure(values=["off", "none", "minimal", "low", "medium", "high", "xhigh"])
                self.codex_visual_reasoning_combo.configure(values=["inherit", "model_default", "none", "minimal", "low", "medium", "high", "xhigh", "max"])
                self.codex_catalog_var.set("Ручной slug вне текущего каталога: доступ/effort не подтверждены. Значение сохранено.")
            return
        selectable = tuple(effort for effort in model.efforts if effort in EFFORTS)
        self.codex_reasoning_combo.configure(values=("off", *selectable))
        self.codex_visual_reasoning_combo.configure(values=("inherit", "model_default", *selectable))
        # A newly selected model must not silently rewrite a user's saved effort.
        reasoning = self.vars["INFINI_LLM_REASONING_MODE"].get()
        visual = self.vars["INFINI_CODEX_VISUAL_REASONING"].get()
        if reasoning not in ("off", *selectable) or visual not in ("inherit", "model_default", *selectable):
            self.codex_catalog_var.set("Сохранённый reasoning не поддерживается выбранной моделью; выбери допустимый effort. Значения не изменены.")
        else:
            self.codex_catalog_var.set(f"Текстовая модель аккаунта: effort {', '.join(selectable) or 'не заявлен'}; default: {model.default_effort or 'не указан'}. Image-доступ не проверен.")

    def codex_login(self):
        from queue import Queue
        from infini_local.services import codex_auth
        if getattr(self, "_codex_login_running", False):
            self.status_var.set("Codex OAuth: вход уже ожидает завершения в браузере.")
            return
        self._codex_login_running = True
        self._codex_login_cancel = threading.Event()
        self._codex_login_results = Queue()
        cancel, results = self._codex_login_cancel, self._codex_login_results
        self.status_var.set("Codex OAuth: заверши вход в открывшемся браузере (3 минуты).")
        def worker():
            try:
                codex_auth.login(cancel=cancel)
                results.put("Codex OAuth: вход выполнен. Выбери openai_codex и сохрани настройки.")
            except codex_auth.CodexError as exc:
                results.put(str(exc))
            except Exception:
                results.put("Codex OAuth: не удалось открыть браузер или сохранить сессию.")
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
        self.status_var.set(result)

    def codex_status(self):
        from infini_local.services.codex_auth import auth_status
        status = auth_status()
        text = "вход не выполнен"
        if status["authenticated"]:
            text = "сессия сохранена; токен обновится при запросе" if status["expired"] else "сессия готова"
        self.status_var.set("Codex OAuth: " + text + ". Квота проверяется сервером при генерации.")

    def codex_logout(self):
        from infini_local.services.codex_auth import logout
        if getattr(self, "_codex_login_running", False):
            self._codex_login_cancel.set()
            self.status_var.set("Codex OAuth: отмена входа; после завершения нажми Sign out ещё раз.")
            return
        try:
            logout()
            # A worker may have fetched the previous account's catalog before
            # sign-out. Retire every queued UI result and remove account metadata.
            self._codex_catalog_generation = getattr(self, "_codex_catalog_generation", 0) + 1
            self._codex_image_ping_generation = getattr(self, "_codex_image_ping_generation", 0) + 1
            self._codex_auto_ping_tabs = set()
            self._codex_text_models = {}
            current = self.vars["INFINI_CODEX_LLM_MODEL"].get().strip()
            self.codex_model_combo.configure(values=[current] if current else [])
            self.codex_catalog_var.set("Сессия удалена; каталог очищен. Сохранённый slug не проверен.")
            self.codex_image_account_var.set("Сессия удалена; image-доступ не проверен.")
            self.status_var.set("Codex OAuth: локальная сессия InfiniCrafter удалена.")
        except OSError:
            self.status_var.set("Codex OAuth: не удалось удалить локальную сессию.")

    def browse_file(self, key: str):
        initial = self.vars[key].get() if key in self.vars else ""
        filename = filedialog.askopenfilename(title="Выбери файл", initialdir=str(Path(initial).parent) if initial else str(ROOT))
        if filename and key in self.vars:
            self.vars[key].set(filename)

    def browse_model(self, key: str):
        initial = self.vars[key].get() if key in self.vars else ""
        filename = filedialog.askopenfilename(title="Выбери model файл", initialdir=str(Path(initial).parent) if initial else str(ROOT), filetypes=[("Model files", "*.gguf *.safetensors *.ckpt *.pt *.pth"), ("All files", "*.*")])
        if filename and key in self.vars:
            self.vars[key].set(filename)

    def browse_lora_file(self) -> bool:
        key = "INFINI_SDCPP_LORA_FILE"
        initial = self.vars[key].get() if key in self.vars else self.data.get("INFINI_SDCPP_LORA_FILE", "")
        initial_dir = str(Path(initial).parent) if initial and Path(initial).suffix else (initial if initial else str(ROOT))
        filename = filedialog.askopenfilename(
            title="Выбери LoRA файл",
            initialdir=initial_dir if Path(initial_dir).exists() else str(ROOT),
            filetypes=[("LoRA files", "*.safetensors *.ckpt *.pt *.pth"), ("All files", "*.*")],
        )
        if filename and key in self.vars:
            self.vars[key].set(filename)
            self.data["INFINI_SDCPP_LORA_DIR"] = str(Path(filename).parent)
            self.status_var.set("LoRA file выбран. Нажми Use selected LoRA, чтобы добавить prompt tag; папка будет взята из файла.")
            return True
        return False

    def browse_folder(self, key: str):
        initial = self.vars[key].get() if key in self.vars else ""
        directory = filedialog.askdirectory(title="Выбери папку", initialdir=initial if initial and Path(initial).exists() else str(ROOT))
        if directory and key in self.vars:
            self.vars[key].set(directory)

    def _server_base_url(self) -> str:
        data = self.collect()
        host = data.get("INFINI_HOST") or "127.0.0.1"
        if host == "0.0.0.0":
            host = "127.0.0.1"
        port = data.get("INFINI_PORT") or "5055"
        return f"http://{host}:{port}"

    @staticmethod
    def _norm_path_for_compare(value: str | Path) -> str:
        # Preserve POSIX case while comparing Windows drive/UNC names under
        # Linux tests too. Never turn a distinct case-sensitive copy into ours.
        text = str(value or "").strip()
        if os.name == "nt" or PureWindowsPath(text).drive:
            return PureWindowsPath(text).as_posix().rstrip("/").casefold()
        return str(Path(text)).rstrip("/")

    @staticmethod
    def _parent_path_text(value: str, levels: int) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        path = PureWindowsPath(text) if (":" in text or "\\" in text) else Path(text)
        for _ in range(levels):
            path = path.parent
        return str(path)

    def _infer_server_root_from_health(self, snap: dict) -> str:
        root = str(snap.get("serverRoot") or "").strip()
        if root:
            return root
        # Fallback path detection: infer LocalGenerator root from cache paths.
        asset_sync = snap.get("assetSync") or {}
        sprite_dir = str(asset_sync.get("spriteDir") or "").strip()
        if sprite_dir:
            return self._parent_path_text(sprite_dir, 2)
        world_recipes = str(snap.get("worldRecipesDir") or "").strip()
        if world_recipes:
            return self._parent_path_text(world_recipes, 2)
        return ""

    def _health_matches_this_gui(self, snap: dict) -> bool:
        # Custom cache roots make cache-derived server-root guesses unsafe.
        # Require the explicit runtime acknowledgement for remote operations.
        root = str(snap.get("serverRoot") or "").strip()
        if not root:
            return False
        return self._norm_path_for_compare(root) == self._norm_path_for_compare(ROOT)

    @staticmethod
    def _health_looks_like_infini_helper(snap: dict) -> bool:
        if not isinstance(snap, dict):
            return False
        # Do not kill arbitrary services that happen to answer {"ok": true} on 5055.
        return bool(
            snap.get("serverRoot")
            or snap.get("cacheDir")
            or snap.get("assetSync")
            or snap.get("pipeline")
            or snap.get("sdcpp")
            or str(snap.get("server_version") or "").lower().startswith("infinicrafter")
        )

    @staticmethod
    def _read_gui_json(url: str, timeout: float, max_bytes: int = 16 * 1024 * 1024) -> dict:
        # Reuse the transport-owned monotonic/redirect/body boundary. A trickled
        # body must not retain a GUI task forever through idle-timeout resets.
        deadline = time.monotonic() + timeout
        with http_io.urlopen_no_redirect(urllib.request.Request(url), deadline=deadline) as response:
            body = http_io.read_with_deadline(response, deadline=deadline, max_bytes=max_bytes)
        value = json.loads(body.decode("utf-8", "replace"))
        if not isinstance(value, dict):
            raise ValueError("GUI diagnostic endpoint returned no object")
        return value

    def _fetch_health_snapshot(self, timeout: float = 8, base_url: str | None = None) -> dict:
        base_url = base_url if base_url is not None else self._server_base_url()
        return self._read_gui_json(base_url + "/health", timeout=timeout)

    def _server_identity_warning(self, snap: dict) -> str:
        root = self._infer_server_root_from_health(snap) or "unknown"
        pid = snap.get("pid") or "unknown"
        return (
            "На этом порту отвечает другая копия InfiniCrafterLocal.\n"
            f"Ответивший server.py: {root}\n"
            f"PID: {pid}\n"
            f"Текущий GUI: {ROOT}\n\n"
            "GUI не будет убивать чужой процесс автоматически. "
            "Останови другую копию вручную или выбери её GUI; Safe/Force restart работают только с текущим root."
        )

    def _server_port(self) -> int:
        try:
            return int((self.collect().get("INFINI_PORT") or "5055").strip())
        except Exception:
            return 5055

    def _try_http_shutdown_current_server(self, timeout: float = 2.0, base_url: str | None = None, force: bool = False) -> tuple[bool, str]:
        base_url = base_url if base_url is not None else self._server_base_url()
        url = base_url + ("/shutdown?force=1" if force else "/shutdown")
        try:
            reply = self._read_gui_json(url, timeout=timeout, max_bytes=64 * 1024)
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
                self._fetch_health_snapshot(timeout=min(0.7, max(0.05, deadline - time.monotonic())), base_url=base_url)
            except Exception as exc:
                # A timeout, 503, malformed JSON or wrong root is not a free port.
                return self._connection_was_refused(exc)
            if cancel is not None:
                cancel.wait(min(0.2, max(0, deadline - time.monotonic())))
            else:
                time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        return False

    def open_sdcpp_start(self):
        self.save()
        webbrowser.open(self._server_base_url() + "/sdcpp_start")
        self.status_var.set("Opened /sdcpp_start. Если server.py ещё не запущен — сначала нажми Start server.")

    def open_sdcpp_debug(self):
        webbrowser.open(self._server_base_url() + "/sdcpp_debug")
        self.status_var.set("Opened /sdcpp_debug.")

    def open_visual_doctor(self):
        webbrowser.open(self._server_base_url() + "/visual_doctor")
        self.status_var.set("Opened /visual_doctor. Если server.py не запущен — Start server.")

    def open_visual_doctor_probe(self):
        webbrowser.open(self._server_base_url() + "/visual_doctor.json?probe=1&role=item")
        self.status_var.set("Opened live item sprite probe. Это реально дергает Z-Image без крафта.")

    def open_config(self):
        if not CONFIG_PATH.exists():
            self.save()
        os.startfile(CONFIG_PATH) if os.name == "nt" else webbrowser.open(CONFIG_PATH.as_uri())

    def open_health(self):
        webbrowser.open(self._server_base_url() + "/health")

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
            lora_dir = self._lora_dir_from_file(lora_file)
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
        if self.radmin_enabled.get() and asset_transport == "http":
            url = data.get("INFINI_ASSET_PUBLIC_BASE_URL", "")
            if not url or "26.x.x.x" in url:
                warnings.append("Radmin/LAN включён, но Public asset URL не заполнен реальным Radmin IP: http://26.xxx.xxx.xxx:5055")
            if data.get("INFINI_HOST") != "0.0.0.0":
                warnings.append("Radmin/LAN включён, но Host не 0.0.0.0 — друзья не достучатся до LocalGenerator asset host.")
        if warnings:
            messagebox.showwarning("Проверка", "\n".join(warnings))
            self.status_var.set("Есть предупреждения по настройкам.")
        else:
            messagebox.showinfo("Проверка", "Критичных проблем в настройках не вижу.")
            self.status_var.set("Проверка прошла без критичных предупреждений.")

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
        self._request_server_action(restart=True)

    def force_restart_server(self):
        if messagebox.askyesno("Force restart", "Прервать активные/ожидающие craft и перезапустить этот server.py?\nГотовность recipe/refund это действие не подтверждает."):
            self._request_server_action(restart=True, force=True)
        else:
            self.status_var.set("Force restart cancelled.")

    @staticmethod
    def _connection_was_refused(exc: Exception) -> bool:
        reason = getattr(exc, "reason", exc)
        return isinstance(reason, ConnectionRefusedError) or getattr(reason, "errno", None) in {111, 61, 10061}

    def _request_server_action(self, restart: bool, force: bool = False):
        if "server-action" in self.__dict__.get("_gui_tasks", {}):
            self.status_var.set("Server action already in progress; wait for its result.")
            return
        base_url = self._server_base_url()
        data = self.collect()
        owned_running = self.proc is not None and self.proc.poll() is None
        self.status_var.set("Force restart: checking identity…" if force else "Safe restart/stop: checking generation activity…")

        def work(cancel):
            try:
                snap = self._fetch_health_snapshot(timeout=2, base_url=base_url)
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
            if not self._wait_until_helper_stops(timeout=4, base_url=base_url, cancel=cancel):
                return "Port still busy: helper has not stopped; no new server launched."
            return ""

        def apply(ok, refusal):
            if not ok or refusal:
                self.status_var.set(refusal if ok else "Safe restart refused: activity unknown.")
                return
            if self.collect() != data:
                self.status_var.set("Restart cancelled: GUI settings changed while checking; start again.")
                return
            if restart:
                self._start_server_after_guard()
            else:
                self.proc = None
                self._cancel_gui_task("health-config")
                self._applied_config_ack = None
                scheduled = self.__dict__.get("_health_after_id")
                if scheduled is not None:
                    self.after_cancel(scheduled)
                    self._health_after_id = None
                self._update_applied_config_feedback("Stopped")
                self.status_var.set("Server stopped through guarded /shutdown.")

        self._run_gui_task("server-action", work, apply)

    def _start_server_after_guard(self):
        # Only the acknowledged shutdown/free-port path reaches launch. Never
        # terminate/kill a PID here: that would bypass atomic busy admission.
        self._cancel_gui_task("health-config")
        self._applied_config_ack = None
        self._update_applied_config_feedback()
        self.save()
        env = os.environ.copy()
        env.update(self.collect())
        cmd = [sys.executable, str(ROOT / "server.py")]
        try:
            options = {"cwd": str(ROOT), "env": env}
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            self.proc = subprocess.Popen(cmd, **options)
            self.status_var.set("server.py запущен. Runtime config ещё не подтверждён.")
            previous = self.__dict__.get("_health_after_id")
            if previous is not None:
                self.after_cancel(previous)
            def check_launched_server():
                self._health_after_id = None
                self._delayed_health_check()
            self._health_after_id = self.after(1000, check_launched_server)
        except Exception:
            messagebox.showerror("Start failed", "Не удалось запустить server.py; проверь Python/права/порт.")
            self.status_var.set("Start failed; runtime config not acknowledged.")

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
            "imageBackend": backend,
            "llmProvider": provider,
            "llmModel": model,
            "openrouterProvider": env.get("INFINI_OPENROUTER_PROVIDER", "").strip() if provider == "openrouter" else "",
            "sdcppAutostart": env.get("INFINI_SDCPP_SERVER_AUTOSTART", "0").strip().lower() in {"1", "true", "yes", "on", "y", "t"},
        }

    def _install_applied_config_tracking(self):
        # Only these non-secret inputs participate in the partial projection.
        # Editing other fields cannot manufacture an acknowledgement of them.
        for key in (
            "INFINI_HOST", "INFINI_PORT", "INFINI_CACHE_DIR", "INFINI_WORLD_RECIPES_DIR",
            "INFINI_IMAGE_BACKEND", "INFINI_LLM_PROVIDER", "INFINI_LMSTUDIO_MODEL",
            "INFINI_OPENROUTER_MODEL", "INFINI_OPENAI_COMPAT_MODEL", "INFINI_CODEX_LLM_MODEL",
            "INFINI_OPENROUTER_PROVIDER", "INFINI_SDCPP_SERVER_AUTOSTART",
        ):
            variable = self.vars.get(key)
            if variable is not None and callable(getattr(variable, "trace_add", None)):
                variable.trace_add("write", lambda *_args: self._update_applied_config_feedback("Edited"))

    def _update_applied_config_feedback(self, state: str = ""):
        prefix = state + "; " if state else ""
        ack = self.__dict__.get("_applied_config_ack")
        if not ack or ack.get("baseUrl") != self._server_base_url():
            self.applied_config_var.set(prefix + "Runtime config unconfirmed (partial non-secret projection; pools/secrets unverified).")
            return
        proposed = self._proposed_effective_config()
        mismatches = [key for key in proposed if proposed[key] != ack["effectiveConfig"].get(key)]
        if mismatches:
            text = "Restart required / runtime mismatch: " + ", ".join(mismatches) + ". Partial non-secret projection; pools/secrets unverified."
        else:
            text = "Runtime matches launch settings at last health check (partial non-secret projection; pools/secrets unverified)."
        self.applied_config_var.set(prefix + text)

    def _delayed_health_check(self):
        # Called by the Tk loop, never a background thread. Capture plain launch
        # inputs here and return results through the same bounded queue pattern.
        if self.__dict__.get("_gui_closed", False):
            return
        base_url = self._server_base_url()
        expected_pid = self.proc.pid if self.proc is not None and self.proc.poll() is None else None
        self.applied_config_var.set("Checking runtime config (partial non-secret projection)…")

        def work(cancel):
            snap = self._fetch_health_snapshot(timeout=3, base_url=base_url)
            if not self._shutdown_identity_is_safe(snap) or (expected_pid is not None and snap.get("pid") != expected_pid):
                return None
            # Drop all other health/config/auth metadata before it enters the UI
            # queue or cached acknowledgement; unexpected fields cannot leak.
            safe = self._safe_effective_config(snap)
            if safe is None:
                return None
            return {"pid": snap.get("pid"), "baseUrl": base_url, "effectiveConfig": safe}

        def apply(ok, ack):
            if not ok or ack is None:
                self._applied_config_ack = None
                self.applied_config_var.set("Runtime config unconfirmed: health/projection unavailable or другая копия (partial; secrets/pools unverified).")
                return
            self._applied_config_ack = ack
            self._update_applied_config_feedback()
            self.status_var.set(self.applied_config_var.get())

        self._run_gui_task("health-config", work, apply)

    def stop_server(self):
        self._request_server_action(restart=False)

    def on_close(self):
        self._gui_closed = True
        health_after = self.__dict__.get("_health_after_id")
        if health_after is not None:
            self.after_cancel(health_after)
            self._health_after_id = None
        for state in self.__dict__.get("_gui_tasks", {}).values():
            state["cancel"].set()
            state["pending"] = None
            if state["after"] is not None:
                self.after_cancel(state["after"])
        self.__dict__.get("_gui_tasks", {}).clear()
        if getattr(self, "_codex_login_running", False):
            self._codex_login_cancel.set()
        self.destroy()

__all__ = ["SettingsGuiServerControlsMixin"]
