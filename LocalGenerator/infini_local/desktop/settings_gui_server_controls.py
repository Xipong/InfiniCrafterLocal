from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path, PureWindowsPath

from infini_local.desktop.tk_compat import filedialog, messagebox, tk, ttk
from infini_local.desktop.settings_schema import (
    DEFAULTS,
    FIELD_HELP,
    FIELD_ORDER,
    OPTION_HELP,
    PRESETS,
    PRESET_HELP,
    SDCPP_DEFAULT_COMMAND_TEMPLATE,
    SDCPP_EXTRA_FLAG_SPECS,
    SDCPP_EXTRA_PROFILES,
    SDCPP_EXTRA_PROFILE_HELP,
    repair_sdcpp_command_template,
)
from infini_local.desktop.settings_env import parse_env, quote_env_value, write_env
from infini_local.desktop.settings_widgets import ScrollFrame, ToolTip
from infini_local.desktop.settings_sdcpp_args import (
    extra_option_names,
    join_extra_for_gui,
    remove_extra_options,
    split_extra_for_gui,
)
from infini_local.desktop.settings_gui_theme import (
    ROOT,
    CONFIG_PATH,
    EXAMPLE_PATH,
    APP_TITLE,
    APP_BG,
    APP_PANEL_BG,
    CARD_BG,
    CARD_MUTED_BG,
    HEADER_BG,
    HEADER_BG_2,
    TEXT_FG,
    MUTED_FG,
    SOFT_FG,
    ACCENT_BG,
    ACCENT_HOVER_BG,
    ACCENT_SOFT_BG,
    ACCENT_FG,
    SUCCESS_BG,
    SUCCESS_SOFT_BG,
    SUCCESS_FG,
    DANGER_BG,
    DANGER_SOFT_BG,
    DANGER_FG,
    WARNING_SOFT_BG,
    WARNING_FG,
    BORDER_FG,
    BORDER_DARK_FG,
)


class SettingsGuiServerControlsMixin:
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
        # Compare Windows paths reliably even when tests run on Linux.
        text = str(value or "").strip().replace("\\", "/")
        while "//" in text and not text.startswith("http"):
            text = text.replace("//", "/")
        return text.rstrip("/").lower()

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
        root = self._infer_server_root_from_health(snap)
        if not root:
            return True
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

    def _fetch_health_snapshot(self, timeout: int = 8) -> dict:
        with urllib.request.urlopen(self._server_base_url() + "/health", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    def _server_identity_warning(self, snap: dict) -> str:
        root = self._infer_server_root_from_health(snap) or "unknown"
        pid = snap.get("pid") or "unknown"
        return (
            "На этом порту отвечает другая копия InfiniCrafterLocal.\n"
            f"Ответивший server.py: {root}\n"
            f"PID: {pid}\n"
            f"Текущий GUI: {ROOT}\n\n"
            "Start server теперь может прибить старый helper автоматически. "
            "Если порт занят не InfiniCrafterLocal, GUI остановится и покажет предупреждение."
        )

    def _server_port(self) -> int:
        try:
            return int((self.collect().get("INFINI_PORT") or "5055").strip())
        except Exception:
            return 5055

    def _try_http_shutdown_current_server(self, timeout: float = 2.0) -> bool:
        try:
            with urllib.request.urlopen(self._server_base_url() + "/shutdown", timeout=timeout) as resp:
                resp.read()
            return True
        except Exception:
            return False

    def _wait_until_helper_stops(self, timeout: float = 4.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self._fetch_health_snapshot(timeout=0.7)
            except Exception:
                return True
            time.sleep(0.2)
        return False

    @staticmethod
    def _pid_command_line(pid: int) -> str:
        if pid <= 0:
            return ""
        if os.name == "nt":
            try:
                cmd = [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine",
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                return (proc.stdout or "").strip()
            except Exception:
                return ""
        try:
            return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except Exception:
            return ""

    @staticmethod
    def _looks_like_infini_server_command(command_line: str) -> bool:
        text = str(command_line or "").replace("\\", "/").lower()
        if not text:
            return False
        if "sd-server" in text or "stable-diffusion" in text:
            return False
        return (
            "infinicrafterlocal" in text
            or ("localgenerator" in text and "server.py" in text)
            or ("infini_local" in text and "web/server" in text)
        )

    @staticmethod
    def _listening_pids_on_port(port: int) -> list[int]:
        pids: set[int] = set()
        try:
            if os.name == "nt":
                proc = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, timeout=4)
                text = proc.stdout or ""
                for line in text.splitlines():
                    cols = line.split()
                    if len(cols) < 5:
                        continue
                    local_addr = cols[1]
                    state = cols[3].upper() if len(cols) >= 5 else ""
                    if state != "LISTENING" or not local_addr.endswith(f":{port}"):
                        continue
                    try:
                        pids.add(int(cols[-1]))
                    except Exception:
                        pass
            else:
                # Best-effort fallback for dev/Linux. Prefer ss, then lsof if present.
                proc = subprocess.run(["bash", "-lc", f"ss -ltnp 'sport = :{port}' 2>/dev/null || true"], capture_output=True, text=True, timeout=4)
                for part in (proc.stdout or "").replace(',', ' ').split():
                    if "pid=" in part:
                        try:
                            pids.add(int(part.split("pid=", 1)[1].split("=", 1)[0].split()[0]))
                        except Exception:
                            pass
        except Exception:
            pass
        return sorted(pid for pid in pids if pid > 0)

    @staticmethod
    def _terminate_pid(pid: int, force: bool = False) -> bool:
        if pid <= 0 or pid == os.getpid():
            return False
        try:
            if os.name == "nt":
                args = ["taskkill", "/PID", str(pid), "/T"]
                if force:
                    args.append("/F")
                subprocess.run(args, capture_output=True, text=True, timeout=5)
            else:
                os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
            return True
        except Exception:
            return False

    def _cleanup_old_helper_servers_before_start(self) -> list[str]:
        """Stop stale LocalGenerator helpers on the configured port before starting.

        Users often close the visible console with the window X, leaving another
        python/server.py copy on 5055.  Start server should behave like restart:
        ask the answering helper to shutdown, then kill only processes that look
        like InfiniCrafterLocal helpers.
        """
        actions: list[str] = []
        snap: dict | None = None
        try:
            snap = self._fetch_health_snapshot(timeout=1.2)
        except Exception:
            snap = None

        if snap and snap.get("ok"):
            if not self._health_looks_like_infini_helper(snap):
                actions.append(f"port {self._server_port()} answers /health but not as InfiniCrafterLocal; not killed")
            else:
                root = self._infer_server_root_from_health(snap) or "unknown"
                pid_raw = snap.get("pid")
                actions.append(f"found helper on {self._server_base_url()} pid={pid_raw or 'unknown'} root={root}")
                if self._try_http_shutdown_current_server(timeout=1.5):
                    actions.append("requested /shutdown")
                    if self._wait_until_helper_stops(timeout=4.0):
                        actions.append("old helper stopped gracefully")
                        return actions
                try:
                    pid = int(pid_raw or 0)
                except Exception:
                    pid = 0
                if pid and pid != os.getpid():
                    if self._terminate_pid(pid, force=False):
                        actions.append(f"sent terminate to pid {pid}")
                        if self._wait_until_helper_stops(timeout=2.0):
                            return actions
                    if self._terminate_pid(pid, force=True):
                        actions.append(f"force-killed pid {pid}")
                        self._wait_until_helper_stops(timeout=2.0)
                        return actions

        port = self._server_port()
        for pid in self._listening_pids_on_port(port):
            if pid == os.getpid():
                continue
            cmdline = self._pid_command_line(pid)
            if self._looks_like_infini_server_command(cmdline):
                if self._terminate_pid(pid, force=False):
                    actions.append(f"sent terminate to stale helper pid {pid}")
                    time.sleep(0.3)
                # If it still listens, force-kill.
                if pid in self._listening_pids_on_port(port):
                    if self._terminate_pid(pid, force=True):
                        actions.append(f"force-killed stale helper pid {pid}")
            else:
                actions.append(f"port {port} is used by non-Infini process pid {pid}; not killed")
        self._wait_until_helper_stops(timeout=2.0)
        return actions

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
            model = data.get("INFINI_SDCPP_MODEL", "")
            vae = data.get("INFINI_SDCPP_VAE", "")
            llm = data.get("INFINI_SDCPP_LLM", "")
            lora_file = data.get("INFINI_SDCPP_LORA_FILE", "")
            lora_dir = self._lora_dir_from_file(lora_file)
            if exe and not Path(exe).exists():
                warnings.append(f"sd-server.exe не найден: {exe}")
            if model and not Path(model).exists():
                warnings.append(f"Z-Image model не найден: {model}")
            if vae and not Path(vae).exists():
                warnings.append(f"Z-Image VAE/AE не найден: {vae}")
            if llm and not Path(llm).exists():
                warnings.append(f"Z-Image Qwen/LLM не найден: {llm}")
            if lora_file and not Path(lora_file).exists():
                warnings.append(f"LoRA file не найден: {lora_file}")
            if lora_file and lora_dir and not Path(lora_dir).exists():
                warnings.append(f"Папка LoRA, выведенная из файла, не найдена: {lora_dir}")
            if data.get("INFINI_SDCPP_LORA_PROMPT_TAGS", "").strip() and not lora_dir:
                warnings.append("LoRA prompt tags заполнены, но LoRA file не выбран — GUI не может вывести --lora-model-dir.")
            if not vae:
                warnings.append("Z-Image VAE/AE пустой: для Z-Image Turbo обычно нужен ae.safetensors.")
            if not llm:
                warnings.append("Z-Image Qwen/LLM пустой: для Z-Image Turbo обычно нужен Qwen3 *.gguf.")
        if data.get("INFINI_LLM_PROVIDER") == "openrouter" and not data.get("INFINI_OPENROUTER_API_KEY"):
            warnings.append("OpenRouter выбран, но API key пустой.")
        if backend == "image_api" and not data.get("INFINI_IMAGE_API_KEY"):
            warnings.append("Image API выбран, но API key пустой.")
        if self.radmin_enabled.get():
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

    def start_server(self):
        self.save()
        cleanup_actions: list[str] = []
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                cleanup_actions.append("terminated GUI-owned server.py")
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    cleanup_actions.append("force-killed GUI-owned server.py")
            except Exception as e:
                cleanup_actions.append(f"failed to stop GUI-owned server.py: {e}")
            self.proc = None
        cleanup_actions.extend(self._cleanup_old_helper_servers_before_start())
        try:
            snap = self._fetch_health_snapshot(timeout=1.5)
            if snap.get("ok"):
                if self._health_looks_like_infini_helper(snap):
                    warning = self._server_identity_warning(snap)
                else:
                    warning = (
                        f"Порт {self._server_port()} занят другим HTTP-сервисом, не похожим на InfiniCrafterLocal.\n"
                        "GUI не будет убивать чужой процесс автоматически."
                    )
                messagebox.showwarning("Port still busy", warning)
                self.status_var.set(f"Порт {self._server_port()} всё ещё занят; новый server.py не запускаю.")
                return
        except Exception:
            pass
        env = os.environ.copy()
        env.update(self.collect())
        cmd = [sys.executable, str(ROOT / "server.py")]
        try:
            if os.name == "nt":
                self.proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                self.proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
            suffix = f" Старые процессы: {'; '.join(cleanup_actions[:3])}" if cleanup_actions else ""
            self.status_var.set("server.py запущен. Health откроется через пару секунд." + suffix)
            threading.Thread(target=self._delayed_health_check, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Start failed", str(e))
            self.status_var.set(f"Start failed: {e}")

    def _delayed_health_check(self):
        time.sleep(2.5)
        url = self._server_base_url() + "/health"
        try:
            snap = self._fetch_health_snapshot(timeout=10)
            if not self._health_matches_this_gui(snap):
                self.status_var.set("Health ответил, но это другая копия server.py на том же порту.")
                return
            self.status_var.set(f"Health OK: {url}")
        except Exception as e:
            self.status_var.set(f"server.py запущен, но health пока не ответил: {e}")

    def stop_server(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.status_var.set("Stop signal sent to server.py")
        else:
            self.status_var.set("Нет server.py процесса, запущенного из этого GUI.")

    def on_close(self):
        self.destroy()

__all__ = ["SettingsGuiServerControlsMixin"]
