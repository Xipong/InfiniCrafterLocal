"""InfiniCrafter-owned ChatGPT OAuth session; never a Platform API key.

Credentials stay outside the project. JWT claims are only expiry/account hints;
OpenAI validates the bearer token. No dependency on Hermes or the Codex CLI.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import re
import secrets
import threading
from urllib import request as urlrequest
from urllib import error as urlerror
from urllib.parse import urlsplit
from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import tempfile
import time


class CodexError(RuntimeError):
    """Safe, credential-free diagnostic for callers and trace logs."""


@dataclass(frozen=True)
class Credentials:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    account_id: str = field(repr=False)
    expires_at: float


# Public native-client identifier from openai/codex (not a client secret).
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TOKEN_URL = "https://auth.openai.com/oauth/token"


@dataclass(frozen=True)
class LoginAttempt:
    port: int = 1455
    verifier: str = field(default_factory=lambda: secrets.token_urlsafe(48), repr=False)
    state: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self.port}/auth/callback"

    @property
    def authorization_url(self) -> str:
        import hashlib
        from urllib.parse import urlencode
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).decode().rstrip("=")
        return "https://auth.openai.com/oauth/authorize?" + urlencode({
            "response_type": "code", "client_id": CLIENT_ID,
            "redirect_uri": self.redirect_uri, "scope": "openid profile email offline_access",
            "code_challenge": challenge, "code_challenge_method": "S256", "state": self.state,
            "id_token_add_organizations": "true", "codex_cli_simplified_flow": "true",
            "originator": "infinicrafter",
        })

    def callback_code(self, target: str) -> str:
        import secrets
        from urllib.parse import parse_qs, urlsplit
        url = urlsplit(target)
        params = parse_qs(url.query, keep_blank_values=True)
        states = params.get("state", [])
        codes = params.get("code", [])
        if url.path != "/auth/callback" or len(states) != 1 or not secrets.compare_digest(states[0], self.state):
            raise CodexError("OAuth callback state mismatch")
        if "error" in params:
            raise CodexError("OAuth sign-in was denied or cancelled")
        if len(codes) != 1:
            raise CodexError("OAuth callback requires exactly one code")
        return _required_text(codes[0], "authorization code")


def auth_path() -> Path:
    return Path.home() / ".infinicrafter" / "codex-auth.json"


def _claims(token: str) -> dict:
    try:
        part = token.split(".")[1]
        value = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return value if isinstance(value, dict) else {}
    except (ValueError, IndexError, UnicodeError):
        return {}


def _required_text(value, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or any(ord(c) < 32 for c in value):
        raise CodexError(f"Invalid OAuth {name}; sign in again")
    return value


def credentials_from_response(data: dict, previous: Credentials | None = None) -> Credentials:
    if not isinstance(data, dict):
        raise CodexError("Invalid OAuth token response")
    access = _required_text(data.get("access_token"), "access token")
    refresh = _required_text(data.get("refresh_token", previous.refresh_token if previous else None), "refresh token")
    claims = _claims(access)
    account_claims = claims.get("https://api.openai.com/auth")
    if not isinstance(account_claims, dict):
        account_claims = _claims(str(data.get("id_token") or "")).get("https://api.openai.com/auth", {})
    account = account_claims.get("chatgpt_account_id") if isinstance(account_claims, dict) else None
    account = _required_text(account or (previous.account_id if previous else None), "account id")
    if previous and account != previous.account_id:
        raise CodexError("OAuth refresh changed account; sign in again")
    expiry = claims.get("exp")
    if expiry is None:
        lifetime = data.get("expires_in")
        if isinstance(lifetime, bool) or not isinstance(lifetime, (float, int)):
            raise CodexError("OAuth token has no valid expiry")
        expiry = time.time() + lifetime
    if isinstance(expiry, bool) or not isinstance(expiry, (float, int)) or not math.isfinite(expiry) or expiry <= time.time():
        raise CodexError("OAuth token is already expired or has invalid expiry")
    return Credentials(access, refresh, account, float(expiry))


def _windows_protect(raw: bytes, *, decrypt: bool = False) -> bytes:
    """DPAPI user-bound protection; Windows credentials cannot be copied to another user."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    windll = getattr(ctypes, "windll")
    function = windll.crypt32.CryptUnprotectData if decrypt else windll.crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise CodexError("Windows could not protect/unprotect the OAuth session")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        windll.kernel32.LocalFree(output.data)


def save_credentials(credentials: Credentials, path: Path | None = None) -> None:
    path = path or auth_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise CodexError("OAuth session path must not be a symlink")
    raw = json.dumps({"version": 1, **asdict(credentials)}, allow_nan=False).encode()
    if os.name == "nt":
        raw = b"ICL-DPAPI\n" + _windows_protect(raw)
    fd, temporary = tempfile.mkstemp(prefix=".codex-auth-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_credentials(path: Path | None = None) -> Credentials:
    path = path or auth_path()
    try:
        if path.is_symlink() or path.stat().st_size > 65536:
            raise CodexError("Invalid OAuth session file")
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise CodexError("OAuth session permissions must be 0600")
        raw = path.read_bytes()
        if raw.startswith(b"ICL-DPAPI\n"):
            if os.name != "nt":
                raise CodexError("Windows OAuth session requires its original Windows user")
            raw = _windows_protect(raw[len(b"ICL-DPAPI\n"):], decrypt=True)
        elif os.name == "nt":
            raise CodexError("Windows OAuth session is not DPAPI protected; sign in again")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("version") != 1:
            raise CodexError("Unsupported OAuth session format")
        expiry = data.get("expires_at")
        if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not math.isfinite(expiry):
            raise CodexError("Invalid OAuth session expiry")
        return Credentials(*(_required_text(data.get(k), k) for k in ("access_token", "refresh_token", "account_id")), expires_at=float(expiry))
    except FileNotFoundError:
        raise CodexError("Codex sign-in required: python -m infini_local.services.codex_auth login") from None
    except (ValueError, TypeError, OSError):
        raise CodexError("Cannot read OAuth session; sign in again") from None


def auth_status(path: Path | None = None) -> dict[str, bool]:
    try:
        credentials = load_credentials(path)
    except CodexError:
        return {"authenticated": False, "expired": False}
    return {"authenticated": True, "expired": credentials.expires_at <= time.time() + 60}


_SESSION_LOCK = threading.RLock()


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _validated_https_origin(url: str) -> None:
    try:
        parsed = urlsplit(url)
        allowed = (parsed.scheme == "https" and parsed.hostname in {"auth.openai.com", "chatgpt.com"}
                   and parsed.username is None and parsed.password is None and parsed.port in (None, 443))
    except ValueError:
        allowed = False
    if not allowed:
        raise CodexError("OAuth transport requires the fixed OpenAI HTTPS origin")


def _decode_unicode_runs(message: str) -> str:
    # Error text and model output can contain nested JSON string literals.
    def decode(match: re.Match) -> str:
        escapes = ''.join('\\u' + code for code in re.findall(r"u([0-9a-fA-F]{4})", match.group(0)))
        return json.loads('"' + escapes + '"').encode("utf-8", "replace").decode("utf-8")

    for _ in range(3):
        decoded = re.sub(r"(?:\\+u[0-9a-fA-F]{4})+", decode, message)
        if decoded == message:
            break
        message = decoded
    return message


def _http_failure(exc: urlerror.HTTPError, payload: dict, headers: dict) -> CodexError:
    # Decode first so JSON escapes cannot hide an echoed credential.
    raw = exc.read(65536)
    try:
        data = json.loads(raw)
        error = data.get("error", data) if isinstance(data, dict) else {}
        message = (str(error.get("message") or json.dumps(error, ensure_ascii=False)) if isinstance(error, dict)
                   else str(error))
    except (ValueError, UnicodeError):
        message = raw.decode("utf-8", "replace")
    message = _decode_unicode_runs(message)
    sensitive = [str(payload[k]) for k in ("refresh_token", "code", "code_verifier") if payload.get(k)]
    for key, value in headers.items():
        if key.lower() in {"authorization", "chatgpt-account-id"}:
            sensitive.extend([value, value.removeprefix("Bearer ")])
    for secret in sorted(sensitive, key=len, reverse=True):
        if secret:
            message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"(?:eyJ[\w-]+\.[\w-]+\.[\w-]+|(?:sk-|rt_)[\w-]{12,})", "[REDACTED]", message)
    message = " ".join(message.split())[:500]
    return CodexError(f"OpenAI HTTP {exc.code}: {message or 'request rejected'}")


def _json_request(url: str, payload: dict, *, method: str, headers: dict | None, timeout: float, limit: int, form: bool = False) -> dict:
    """Bounded JSON transport, no redirects, credentials never reach another origin."""
    _validated_https_origin(url)
    merged = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "infinicrafter/1.0", **(headers or {})}
    raw_payload = None
    if method == "POST":
        if form:
            from urllib.parse import urlencode
            merged["Content-Type"] = "application/x-www-form-urlencoded"
            raw_payload = urlencode(payload).encode()
        else:
            raw_payload = json.dumps(payload).encode()
    req = urlrequest.Request(url, data=raw_payload, headers=merged, method=method)
    try:
        with urlrequest.build_opener(_NoRedirect()).open(req, timeout=timeout) as response:
            raw = response.read(limit + 1)
        if len(raw) > limit:
            raise CodexError("OpenAI response exceeded the size limit")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise CodexError("OpenAI response must be a JSON object")
        return result
    except urlerror.HTTPError as exc:
        raise _http_failure(exc, payload, merged) from None
    except (ValueError, UnicodeError):
        raise CodexError("OpenAI returned invalid JSON") from None
    except (urlerror.URLError, OSError):
        raise CodexError("OpenAI connection failed or timed out") from None


def post_json(url: str, payload: dict, *, headers: dict | None = None, timeout: float = 30, limit: int = 65536, form: bool = False) -> dict:
    return _json_request(url, payload, method="POST", headers=headers, timeout=timeout, limit=limit, form=form)


def get_json(url: str, *, headers: dict | None = None, timeout: float = 8, limit: int = 1024 * 1024) -> dict:
    return _json_request(url, {}, method="GET", headers=headers, timeout=timeout, limit=limit)


def post_sse(url: str, payload: dict, *, headers: dict | None = None, timeout: float = 120, limit: int = 8 * 1024 * 1024) -> dict:
    """Read the native subscription Responses stream; partial output is never success."""
    if url != "https://chatgpt.com/backend-api/codex/responses" or payload.get("stream") is not True:
        raise CodexError("Codex text requires the fixed streaming subscription endpoint")
    _validated_https_origin(url)
    merged = {"Content-Type": "application/json", "Accept": "text/event-stream", "User-Agent": "infinicrafter/1.0", **(headers or {})}
    req = urlrequest.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=merged, method="POST")
    deadline = time.monotonic() + timeout
    try:
        with urlrequest.build_opener(_NoRedirect()).open(req, timeout=timeout) as response:
            total = 0
            data_lines: list[bytes] = []
            completed_items: list[dict] = []
            text_deltas: list[str] = []
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CodexError("Codex text stream timed out")
                # urllib sets a socket timeout per read, not for the whole SSE
                # request. Reduce every network read to the remaining budget.
                sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                if sock is not None:
                    sock.settimeout(max(0.001, remaining))
                line = response.readline(256 * 1024 + 1)
                if time.monotonic() > deadline:
                    raise CodexError("Codex text stream timed out")
                total += len(line)
                if total > limit or len(line) > 256 * 1024:
                    raise CodexError("Codex text stream exceeded its size limit")
                if not line:
                    break
                if line.startswith(b"data:"):
                    data_lines.append(line[5:].strip())
                    continue
                if line.strip() or not data_lines:
                    continue
                raw = b"\n".join(data_lines)
                data_lines.clear()
                if raw == b"[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise CodexError("Codex returned malformed stream data") from None
                if not isinstance(event, dict):
                    raise CodexError("Codex returned malformed stream data")
                kind = event.get("type")
                if kind == "response.output_item.done" and isinstance(event.get("item"), dict):
                    completed_items.append(event["item"])
                if kind == "response.output_text.delta" and isinstance(event.get("delta"), str):
                    text_deltas.append(event["delta"])
                if kind in {"response.failed", "response.incomplete", "error"}:
                    raise CodexError("Codex text response failed or was incomplete")
                if kind == "response.completed":
                    result = event.get("response")
                    if not isinstance(result, dict) or result.get("status") not in (None, "completed"):
                        raise CodexError("Codex text completion was invalid")
                    if not result.get("output"):
                        result["output"] = completed_items or ([{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "".join(text_deltas)}]}] if text_deltas else [])
                    return result
            raise CodexError("Codex text stream ended before completion")
    except urlerror.HTTPError as exc:
        raise _http_failure(exc, payload, merged) from None
    except (urlerror.URLError, OSError):
        raise CodexError("Codex text connection failed or timed out") from None


@contextmanager
def session_lock(path: Path):
    """Serialize refresh/logout/login across threads and generator/GUI processes."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = path.with_suffix(".lock")
    if lock_path.is_symlink():
        raise CodexError("OAuth lock path must not be a symlink")
    with _SESSION_LOCK, open(lock_path, "a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            deadline = time.monotonic() + 60
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise CodexError("OAuth session is busy; retry later") from None
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def get_credentials(path: Path | None = None) -> Credentials:
    path = path or auth_path()
    with session_lock(path):
        current = load_credentials(path)
        if current.expires_at > time.time() + 60:
            return current
        result = post_json(TOKEN_URL, {"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": current.refresh_token})
        refreshed = credentials_from_response(result, previous=current)
        save_credentials(refreshed, path)
        return refreshed


def login(*, path: Path | None = None, on_url=None, open_browser: bool = True, port: int = 1455, timeout: float = 180, cancel=None) -> None:
    """Browser PKCE flow on loopback only. Never log callback queries or tokens."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import webbrowser

    path = path or auth_path()
    completed = False
    failure = None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            nonlocal completed, failure
            try:
                if self.headers.get("Host") not in {f"localhost:{attempt.port}", f"127.0.0.1:{attempt.port}"}:
                    raise CodexError("Invalid callback host")
                code = attempt.callback_code(self.path)
            except CodexError:
                self.send_error(400, "Invalid or denied OAuth callback")
                return
            try:
                with session_lock(path):
                    response = post_json(TOKEN_URL, {
                        "grant_type": "authorization_code", "client_id": CLIENT_ID,
                        "code": code, "code_verifier": attempt.verifier,
                        "redirect_uri": attempt.redirect_uri,
                    }, form=True)
                    save_credentials(credentials_from_response(response), path)
                completed = True
                body = b"InfiniCrafter sign-in complete. You may close this window."
                status = 200
            except (CodexError, OSError) as exc:
                failure = exc if isinstance(exc, CodexError) else CodexError("Could not save OAuth session")
                body = b"InfiniCrafter sign-in failed. Check the application."
                status = 400
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    class CallbackServer(HTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(5)
            return connection, address

        def handle_error(self, request, client_address):
            # Base implementation prints tracebacks from the credential exchange.
            pass

    try:
        server = CallbackServer(("127.0.0.1", port), Handler)
    except OSError:
        raise CodexError("OAuth loopback port is busy; close the other login and retry") from None
    with server:
        attempt = LoginAttempt(port=server.server_port)
        server.timeout = 0.2
        if on_url:
            on_url(attempt.authorization_url)
        if open_browser:
            webbrowser.open(attempt.authorization_url)
        deadline = time.monotonic() + timeout
        while not completed and failure is None:
            if (cancel is not None and cancel.is_set()) or time.monotonic() >= deadline:
                raise CodexError("OAuth login cancelled or timed out")
            server.handle_request()
    if failure:
        raise failure


def logout(path: Path | None = None) -> None:
    path = path or auth_path()
    with session_lock(path):
        path.unlink(missing_ok=True)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="InfiniCrafter ChatGPT/Codex OAuth; no API key")
    parser.add_argument("command", choices=("login", "status", "logout"))
    args = parser.parse_args()
    try:
        if args.command == "login":
            login(on_url=lambda url: print("Open in your browser: " + url, flush=True))
        elif args.command == "logout":
            logout()
        print(json.dumps(auth_status()))
        return 0
    except (CodexError, OSError) as exc:
        print(str(exc) if isinstance(exc, CodexError) else "Could not access the OAuth session file")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
