from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows uses msvcrt below.
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX uses fcntl above.
    msvcrt = None  # type: ignore[assignment]


# All in-process trace writers share this lock.  Rotation is deliberately part
# of the same critical section as append so a rename can never split an NDJSON
# record written by another request thread.
_NDJSON_WRITE_LOCK = threading.RLock()
_NDJSON_MAX_BYTES = 16 * 1024 * 1024
_NDJSON_BACKUP_COUNT = 2
_TAIL_READ_CHUNK_BYTES = 64 * 1024


@contextmanager
def _ndjson_process_lock(path: Path) -> Iterator[None]:
    """Serialize append/recovery/rotation across LocalGenerator processes."""
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            if msvcrt is None:  # pragma: no cover - defensive platform guard.
                raise RuntimeError("msvcrt is required for Windows trace locking")
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            if fcntl is None:  # pragma: no cover - defensive platform guard.
                raise RuntimeError("fcntl is required for POSIX trace locking")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _ndjson_backup_path(path: Path, index: int) -> Path:
    return path.with_name(f"{path.name}.{index}")


def _parse_ndjson_line(line: bytes) -> Any | None:
    if not line or b"\x00" in line:
        return None
    try:
        return json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _recover_ndjson_locked(path: Path) -> bool:
    """Drop only a corrupt final suffix while keeping the normal append path O(tail)."""
    if not path.exists():
        return False
    with path.open("r+b") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        if size == 0:
            return False

        position = size
        buffered = b""
        while position > 0:
            start = max(0, position - _TAIL_READ_CHUNK_BYTES)
            handle.seek(start)
            buffered = handle.read(position - start) + buffered
            pieces = buffered.splitlines(keepends=True)
            offset = 0
            candidates: list[tuple[int, bytes]] = []
            for index, line in enumerate(pieces):
                end = start + offset + len(line)
                offset += len(line)
                # The first line of a non-zero chunk may begin in the middle of a
                # record. It becomes eligible after the preceding chunk is loaded.
                if start > 0 and index == 0:
                    continue
                if not line.endswith((b"\n", b"\r")):
                    continue
                record = line.rstrip(b"\r\n")
                if record and _parse_ndjson_line(record) is not None:
                    candidates.append((end, record))
            if candidates:
                valid_end = candidates[-1][0]
                if valid_end == size:
                    return False
                handle.truncate(valid_end)
                return True
            position = start

        handle.truncate(0)
        return True


def recover_ndjson(path: str | Path) -> bool:
    """Repair a trailing NDJSON corruption suffix without touching prior rows."""
    try:
        target = Path(path)
        with _NDJSON_WRITE_LOCK, _ndjson_process_lock(target):
            return _recover_ndjson_locked(target)
    except Exception:
        return False


def _rotate_ndjson_locked(path: Path, backup_count: int) -> None:
    backups = max(0, int(backup_count))
    if backups == 0:
        path.unlink(missing_ok=True)
        return
    for index in range(backups, 1, -1):
        previous = _ndjson_backup_path(path, index - 1)
        if previous.exists():
            os.replace(previous, _ndjson_backup_path(path, index))
    os.replace(path, _ndjson_backup_path(path, 1))


def append_ndjson(
    path: str | Path,
    record: Any,
    *,
    max_bytes: int = _NDJSON_MAX_BYTES,
    backup_count: int = _NDJSON_BACKUP_COUNT,
) -> None:
    """Append one complete JSON record through the process-wide rotation lock."""
    target = Path(path)
    encoded = (json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str) + "\n").encode("utf-8")
    with _NDJSON_WRITE_LOCK, _ndjson_process_lock(target):
        target.parent.mkdir(parents=True, exist_ok=True)
        _recover_ndjson_locked(target)
        limit = max(1, int(max_bytes))
        if target.exists() and target.stat().st_size and target.stat().st_size + len(encoded) > limit:
            _rotate_ndjson_locked(target, backup_count)
        with target.open("ab") as handle:
            handle.write(encoded)


def clear_ndjson(path: str | Path) -> None:
    """Clear one trace file under the same lock used by append and rotation."""
    target = Path(path)
    with _NDJSON_WRITE_LOCK, _ndjson_process_lock(target):
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb"):
            pass


def initialize_trace_storage(paths: list[str | Path] | tuple[str | Path, ...]) -> dict[str, bool]:
    """Repair bounded trace tails once during application startup."""
    return {str(Path(path)): recover_ndjson(path) for path in paths}


def json_slim(obj: Any, max_chars: int = 40000) -> Any:
    """Return a JSON-safe, size-bounded debug object for failure traces."""
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)[:max_chars]
    if len(text) <= max_chars:
        try:
            return json.loads(text)
        except Exception:
            return text
    return {"_truncated": True, "jsonPrefix": text[:max_chars]}


def log_event(cache_dir: Path, level: str, message: str, payload: Any = None) -> None:
    """Append human-readable diagnostics to cache/events.ndjson."""
    try:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "createdAt": time.time(),
            "level": str(level),
            "message": str(message),
            "payload": payload,
        }
        append_ndjson(cache_dir / "events.ndjson", event)
    except Exception:
        pass


def trace_clip(value: Any, *, default_max_chars: int, max_chars: int | None = None) -> str:
    limit = int(default_max_chars) if max_chars is None else max(200, int(max_chars))
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str, indent=2)
    except Exception:
        text = str(value)
    if len(text) > limit:
        return text[:limit] + "\n...<clipped " + str(len(text) - limit) + " chars>"
    return text


def trace_message_summary(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, m in enumerate(messages or []):
        content = str((m or {}).get("content") or "")
        out.append({
            "index": i,
            "role": str((m or {}).get("role") or ""),
            "name": str((m or {}).get("name") or ""),
            "chars": len(content),
            "preview": content[:420],
        })
    return out


def trace_event(
    *,
    cache_dir: Path,
    trace_prompts_enabled: bool,
    trace_max_prompt_chars: int,
    trace_file: Path,
    prompt_trace_file: Path,
    kind: str,
    stage: str,
    title: str,
    payload: Any = None,
    prompt: Any = None,
    negative: Any = None,
    response: Any = None,
    error: Any = None,
) -> None:
    if not trace_prompts_enabled and kind in {"prompt", "response"}:
        return
    try:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        event: dict[str, Any] = {"ts": int(time.time()), "kind": str(kind), "stage": str(stage), "title": str(title)}
        if payload is not None:
            event["payload"] = json_slim(payload, 24000)
        if prompt is not None:
            event["prompt"] = trace_clip(prompt, default_max_chars=trace_max_prompt_chars)
        if negative is not None:
            event["negative"] = trace_clip(negative, default_max_chars=trace_max_prompt_chars, max_chars=6000)
        if response is not None:
            event["response"] = trace_clip(response, default_max_chars=trace_max_prompt_chars)
        if error is not None:
            event["error"] = trace_clip(error, default_max_chars=trace_max_prompt_chars, max_chars=6000)
        target = prompt_trace_file if kind in {"prompt", "response"} or prompt is not None else trace_file
        append_ndjson(target, event)
    except Exception:
        pass


def tail_text_file(path: str | Path, max_chars: int = 16000) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return ""
        byte_limit = max(1, int(max_chars)) * 4 + 4
        with p.open("rb") as handle:
            handle.seek(0, 2)
            start = max(0, handle.tell() - byte_limit)
            handle.seek(start)
            text = handle.read().decode("utf-8", errors="replace")
        return text[-max_chars:]
    except Exception as e:
        return f"<tail failed: {e!r}>"


def tail_ndjson(path: str | Path, limit: int = 80) -> list[dict[str, Any]]:
    try:
        p = Path(path)
        if not p.exists():
            return []
        wanted = max(1, int(limit))
        lines: list[bytes] = []
        needs_recovery = False
        with _NDJSON_WRITE_LOCK, _ndjson_process_lock(p), p.open("rb") as handle:
            handle.seek(0, 2)
            position = handle.tell()
            if position == 0:
                return []
            handle.seek(position - 1)
            discard_final_fragment = handle.read(1) != b"\n"
            needs_recovery = discard_final_fragment
            buffered = b""
            while position > 0 and len(lines) < wanted:
                start = max(0, position - _TAIL_READ_CHUNK_BYTES)
                handle.seek(start)
                buffered = handle.read(position - start) + buffered
                pieces = buffered.split(b"\n")
                if start > 0:
                    buffered = pieces[0]
                    complete = pieces[1:]
                else:
                    buffered = b""
                    complete = pieces
                for line in reversed(complete):
                    if discard_final_fragment:
                        discard_final_fragment = False
                        continue
                    if line.endswith(b"\r"):
                        line = line[:-1]
                    if line:
                        lines.append(line)
                        if len(lines) >= wanted:
                            break
                position = start
        out: list[dict[str, Any]] = []
        for line in reversed(lines):
            if not line.strip():
                continue
            if b"\x00" in line:
                needs_recovery = True
                continue
            try:
                obj = json.loads(line.decode("utf-8"))
                out.append(obj if isinstance(obj, dict) else {"raw": obj})
            except (UnicodeDecodeError, json.JSONDecodeError):
                needs_recovery = True
        if needs_recovery:
            recover_ndjson(p)
        return out
    except Exception as e:
        return [{"level": "error", "message": "trace read failed", "error": repr(e)}]
