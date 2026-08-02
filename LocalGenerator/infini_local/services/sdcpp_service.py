from __future__ import annotations

import atexit
from contextlib import contextmanager
import os
import signal
import subprocess
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class ImageRequestGate:
    """Bound all image-backend calls that share one GPU/server.

    Multi-dev craft lanes may run their LLM stages in parallel, but they must not
    submit an unbounded burst to the same diffusion process. This gate owns only
    backend request admission; model semantics and asset-role selection stay in
    the visual pipeline.
    """

    def __init__(self, capacity: int) -> None:
        self.capacity = max(1, int(capacity))
        self._semaphore = threading.BoundedSemaphore(self.capacity)

    @contextmanager
    def slot(self):
        self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()


@dataclass
class SdcppServerState:
    """Mutable lifecycle state for the optional persistent stable-diffusion.cpp server.

    Keep this state outside server.py so the HTTP entrypoint can stay focused on routing
    and pipeline orchestration while the image-backend adapter owns lifecycle calls.
    """

    process: subprocess.Popen | None = None
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    cleanup_registered: bool = False
    signal_handlers_registered: bool = False
    previous_signal_handlers: dict[int, Any] = field(default_factory=dict, repr=False)
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


def _close_process_log_handle(proc: subprocess.Popen | Any) -> None:
    handle = getattr(proc, "_infini_log_handle", None)
    if handle is None:
        return
    try:
        handle.close()
    except (OSError, ValueError):
        pass


def _terminate_process_tree(proc: subprocess.Popen | Any, *, hard: bool) -> None:
    """Terminate the sd.cpp process and children without leaking helper processes.

    sd-server may be launched through WSL interop, cmd.exe, or a wrapper script. Killing
    only the immediate Popen object can leave the real model process alive, which in turn
    keeps tests/Python shutdown hanging and makes the next autostart race for the port.
    """
    if proc.poll() is not None:
        return
    if os.name == "nt":
        # Always target the whole Windows process tree. A wrapper can exit quickly while
        # the real sd-server child keeps the port/VRAM alive, so waiting for a timeout
        # before using /T is too late.
        command = ["taskkill", "/PID", str(proc.pid), "/T"]
        if hard:
            command.append("/F")
        try:
            subprocess.run(
                command,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return
        except (OSError, subprocess.SubprocessError):
            proc.kill() if hard else proc.terminate()
        return

    grouped = bool(getattr(proc, "_infini_process_group", False))
    if grouped:
        try:
            os.killpg(proc.pid, signal.SIGKILL if hard else signal.SIGTERM)
            return
        except ProcessLookupError:
            return
        except OSError:
            pass
    proc.kill() if hard else proc.terminate()


def cleanup_server_process(state: SdcppServerState, log_event: LogEvent, reason: str = "cleanup") -> None:
    with state.lock:
        proc = state.process
        if proc is None:
            return
        state.process = None
        try:
            if proc.poll() is None:
                log_event("info", "terminating stable-diffusion.cpp server", {"reason": reason, "pid": getattr(proc, "pid", None)})
                _terminate_process_tree(proc, hard=False)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log_event("warn", "stable-diffusion.cpp server did not terminate; killing process tree", {"reason": reason, "pid": getattr(proc, "pid", None)})
                    _terminate_process_tree(proc, hard=True)
                    try:
                        proc.wait(timeout=3)
                    except (subprocess.TimeoutExpired, OSError):
                        pass
        except (OSError, subprocess.SubprocessError) as e:
            log_event("warn", "stable-diffusion.cpp cleanup failed", {"reason": reason, "error": repr(e)})
        finally:
            _close_process_log_handle(proc)


def install_cleanup_handlers(state: SdcppServerState, cleanup_process: CleanupProcess) -> None:
    with state.lock:
        if not state.cleanup_registered:
            state.cleanup_registered = True
            atexit.register(lambda: cleanup_process("atexit"))

        # Python only permits signal registration on the main thread. A worker
        # may install atexit first; a later main-thread autostart must still get
        # its signal handlers, hence the separate registration flag.
        if state.signal_handlers_registered or threading.current_thread() is not threading.main_thread():
            return

        registered_any = False
        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is None:
                continue
            try:
                previous = signal.getsignal(sig)
                state.previous_signal_handlers[int(sig)] = previous

                def _handler(signum, frame, previous=previous):
                    cleanup_process(f"signal:{signum}")
                    if callable(previous):
                        previous(signum, frame)
                        return
                    if previous == signal.SIG_IGN:
                        return
                    if signum == getattr(signal, "SIGINT", None):
                        raise KeyboardInterrupt
                    raise SystemExit(128 + int(signum))

                signal.signal(sig, _handler)
                registered_any = True
            except (ValueError, OSError, RuntimeError):
                pass
        state.signal_handlers_registered = registered_any


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
        install_cleanup_handlers(state, cleanup_process)
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
        log_handle = None
        spawned_process: subprocess.Popen | None = None
        try:
            creationflags = 0
            stdout_target = None
            stderr_target = None
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
            start_new_session = os.name != "nt"
            if os.name == "nt" and not show_console:
                creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            spawned_process = subprocess.Popen(
                cmd,
                shell=shell,
                cwd=str(root),
                env=process_env,
                stdout=stdout_target,
                stderr=stderr_target,
                text=False if stdout_target is None else True,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
            state.process = spawned_process
            setattr(spawned_process, "_infini_process_group", bool(start_new_session or creationflags & getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)))
            # The Popen object does not keep this handle alive reliably across implementations if it is GC'd.
            # Store it as a private attribute so logs keep flowing while the process lives.
            if log_handle is not None:
                setattr(spawned_process, "_infini_log_handle", log_handle)
        except Exception as e:
            state.process = None
            if spawned_process is not None:
                try:
                    _terminate_process_tree(spawned_process, hard=True)
                    spawned_process.wait(timeout=3)
                except (OSError, subprocess.SubprocessError):
                    pass
                finally:
                    _close_process_log_handle(spawned_process)
            if log_handle is not None and not log_handle.closed:
                try:
                    log_handle.close()
                except (OSError, ValueError):
                    pass
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
                cleanup_process("startup_exited")
                return False
            time.sleep(1.0)
        state.last_start_error = f"startup timeout after {startup_timeout}s"
        timeout_tail = tail_text_file(state.last_log_file, 16000)[-2000:]
        log_event("warn", "stable-diffusion.cpp server startup timeout", {"url": server_url, "timeout": startup_timeout, "cmd": state.last_command, "logFile": state.last_log_file, "logTail": timeout_tail})
        cleanup_process("startup_timeout")
        return False
