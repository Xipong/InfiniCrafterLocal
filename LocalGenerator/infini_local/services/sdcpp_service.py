from __future__ import annotations

import atexit
import os
import signal
import subprocess
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class SdcppServerState:
    """Mutable lifecycle state for the optional persistent stable-diffusion.cpp server.

    Keep this state outside server.py so the HTTP entrypoint can stay focused on routing
    and pipeline orchestration while the image-backend adapter owns lifecycle calls.
    """

    process: subprocess.Popen | None = None
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    cleanup_registered: bool = False
    last_command: str = ""
    last_log_file: str = ""
    last_start_error: str = ""
    last_exit: dict[str, Any] = field(default_factory=dict)


LogEvent = Callable[[str, str, Any], None]
TailTextFile = Callable[[str | Path, int], str]
ServerIsAlive = Callable[[], bool]
BuildCommand = Callable[[], tuple[list[str] | str, bool]]
StringifyCommand = Callable[[list[str] | str], str]
ServerIsConfigured = Callable[[], bool]
CleanupProcess = Callable[[str], None]


def cleanup_server_process(state: SdcppServerState, log_event: LogEvent, reason: str = "cleanup") -> None:
    with state.lock:
        proc = state.process
        if proc is None:
            return
        state.process = None
        try:
            if proc.poll() is None:
                log_event("info", "terminating stable-diffusion.cpp server", {"reason": reason})
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log_event("warn", "stable-diffusion.cpp server did not terminate; killing", {"reason": reason})
                    proc.kill()
                    try:
                        proc.wait(timeout=3)
                    except Exception:
                        pass
        except Exception as e:
            log_event("warn", "stable-diffusion.cpp cleanup failed", {"reason": reason, "error": repr(e)})
        finally:
            handle = getattr(proc, "_infini_log_handle", None)
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass


def install_cleanup_handlers(state: SdcppServerState, cleanup_process: CleanupProcess) -> None:
    if state.cleanup_registered:
        return
    state.cleanup_registered = True
    atexit.register(lambda: cleanup_process("atexit"))
    # Windows supports SIGINT/SIGTERM in normal console runs; if a host forbids
    # signal handlers, keep atexit cleanup and continue.
    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is None:
            continue
        try:
            previous = signal.getsignal(sig)

            def _handler(signum, frame, previous=previous):
                cleanup_process(f"signal:{signum}")
                if callable(previous):
                    previous(signum, frame)
                else:
                    raise KeyboardInterrupt

            signal.signal(sig, _handler)
        except Exception:
            pass


def debug_snapshot(
    *,
    state: SdcppServerState,
    app_version: str,
    server_url: str,
    server_autostart: bool,
    show_console: bool,
    server_exe: str,
    model: str,
    vae: str,
    llm: str,
    lora_dir: str,
    lora_prompt_tags: str,
    lora_file: str = "",
    lora_weight: str = "",
    command_mode: str,
    command_template: str,
    template_repair: tuple[str, bool, str],
    manual_extra_args: str,
    effective_extra_args: str,
    command: str,
    server_log_file: str,
    server_is_alive: bool,
    server_is_configured: bool,
    tail_text_file: TailTextFile,
    include_log_tail: bool = True,
) -> dict[str, Any]:
    proc_alive = False
    proc_returncode = None
    try:
        if state.process is not None:
            proc_returncode = state.process.poll()
            proc_alive = proc_returncode is None
    except Exception:
        pass
    log_file = state.last_log_file or server_log_file
    return {
        "ok": True,
        "version": app_version,
        "serverUrl": server_url,
        "serverAlive": server_is_alive,
        "serverConfigured": server_is_configured,
        "autostart": server_autostart,
        "showConsole": show_console,
        "processAlive": proc_alive,
        "processReturncode": proc_returncode,
        "serverExe": server_exe,
        "model": model,
        "vae": vae,
        "llm": llm,
        "loraDir": lora_dir,
        "loraFile": lora_file,
        "loraWeight": lora_weight,
        "loraPromptTags": lora_prompt_tags,
        "commandMode": command_mode,
        "commandTemplate": command_template,
        "templateRepair": template_repair,
        "manualExtraArgs": manual_extra_args,
        "effectiveExtraArgs": effective_extra_args,
        "command": state.last_command or command,
        "logFile": log_file,
        "lastStartError": state.last_start_error,
        "lastExit": state.last_exit,
        "logTail": tail_text_file(log_file, 16000) if include_log_tail and log_file else "",
    }


def ensure_server(
    *,
    state: SdcppServerState,
    root: Path,
    cache_dir: Path,
    server_url: str,
    server_autostart: bool,
    startup_timeout: int,
    show_console: bool,
    server_log_file: str,
    server_is_alive: ServerIsAlive,
    build_command: BuildCommand,
    stringify_cmd: StringifyCommand,
    cleanup_process: CleanupProcess,
    log_event: LogEvent,
    tail_text_file: TailTextFile,
    process_env: dict[str, str] | None = None,
) -> bool:
    """Ensure persistent sd.cpp server is alive, optionally autostarting it."""
    with state.lock:
        state.last_start_error = ""
        if server_is_alive():
            return True
        if not server_autostart:
            return False
        # If old child died or became unhealthy, forget/cleanup it before restarting.
        if state.process is not None:
            try:
                if state.process.poll() is None:
                    # Process exists but health failed; give it a brief moment before restarting.
                    time.sleep(0.5)
                    if server_is_alive():
                        return True
            except Exception:
                pass
            cleanup_process("restart_unhealthy")
        cmd, shell = build_command()
        state.last_command = stringify_cmd(cmd)
        log_path = Path(server_log_file) if server_log_file else (cache_dir / "sdcpp_server.log")
        state.last_log_file = str(log_path)
        log_event("info", "starting stable-diffusion.cpp persistent server", {"cmd": state.last_command, "shell": shell, "url": server_url, "showConsole": show_console, "logFile": state.last_log_file})
        try:
            creationflags = 0
            stdout_target = None
            stderr_target = None
            log_handle = None
            if os.name == "nt" and show_console:
                # Let sd-server own a visible console. This prevents stdout PIPE deadlocks and gives the user live logs.
                creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            else:
                # Headless mode: redirect logs to a file, never to PIPE. PIPE can block verbose model startup.
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_handle = open(log_path, "a", encoding="utf-8", errors="replace")
                log_handle.write("\n\n===== sd.cpp start " + time.strftime("%Y-%m-%d %H:%M:%S") + " =====\n")
                log_handle.write(state.last_command + "\n")
                log_handle.flush()
                stdout_target = log_handle
                stderr_target = subprocess.STDOUT
            state.process = subprocess.Popen(
                cmd,
                shell=shell,
                cwd=str(root),
                env=process_env,
                stdout=stdout_target,
                stderr=stderr_target,
                text=False if stdout_target is None else True,
                creationflags=creationflags,
            )
            # The Popen object does not keep this handle alive reliably across implementations if it is GC'd.
            # Store it as a private attribute so logs keep flowing while the process lives.
            if log_handle is not None:
                setattr(state.process, "_infini_log_handle", log_handle)
        except Exception as e:
            state.last_start_error = repr(e)
            log_event("warn", "failed to start stable-diffusion.cpp server", {"error": state.last_start_error, "cmd": state.last_command, "logFile": state.last_log_file})
            return False
        deadline = time.time() + max(5, startup_timeout)
        while time.time() < deadline:
            if server_is_alive():
                log_event("info", "stable-diffusion.cpp server is ready", {"url": server_url, "logFile": state.last_log_file})
                return True
            if state.process is not None and state.process.poll() is not None:
                state.last_exit = {
                    "returncode": state.process.returncode,
                    "logTail": tail_text_file(state.last_log_file, 16000),
                }
                log_event("warn", "stable-diffusion.cpp server exited during startup", {"returncode": state.process.returncode, "logFile": state.last_log_file, "logTail": state.last_exit.get("logTail", "")[-2000:]})
                return False
            time.sleep(1.0)
        state.last_start_error = f"startup timeout after {startup_timeout}s"
        log_event("warn", "stable-diffusion.cpp server startup timeout", {"url": server_url, "timeout": startup_timeout, "cmd": state.last_command, "logFile": state.last_log_file, "logTail": tail_text_file(state.last_log_file, 16000)[-2000:]})
        return False
