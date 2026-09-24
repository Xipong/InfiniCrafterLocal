from __future__ import annotations

import base64
import importlib
import importlib.util
import json
import os
import stat
import time

import pytest
from urllib.parse import parse_qs, urlsplit


def auth_module():
    name = "infini_local.services.codex_auth"
    assert importlib.util.find_spec(name) is not None, "native Codex OAuth owner is missing"
    return importlib.import_module(name)


def jwt(claims):
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return "test." + body + ".unsigned"


def token_response():
    return {"access_token": jwt({"exp": int(time.time()) + 3600, "https://api.openai.com/auth": {"chatgpt_account_id": "test-account"}}),
            "refresh_token": "test-refresh-not-real", "expires_in": 3600}


def test_pkce_callback_is_state_bound_and_secrets_do_not_appear_in_repr():
    auth = auth_module()
    assert hasattr(auth, "LoginAttempt"), "PKCE login is not implemented"
    attempt = auth.LoginAttempt()
    params = parse_qs(urlsplit(attempt.authorization_url).query)
    import hashlib
    expected = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode()).digest()).decode().rstrip("=")
    assert params["code_challenge"] == [expected]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://localhost:1455/auth/callback"]
    assert params["scope"] == ["openid profile email offline_access"]
    assert attempt.verifier not in repr(attempt)
    for suffix in ("state=wrong&code=x", f"state={attempt.state}&state=wrong&code=x", f"state={attempt.state}&code=x&code=y"):
        with pytest.raises(auth.CodexError):
            attempt.callback_code("/auth/callback?" + suffix)
    assert attempt.callback_code(f"/auth/callback?state={attempt.state}&code=test-code") == "test-code"


def test_expired_session_refreshes_once_under_concurrent_requests(tmp_path, monkeypatch):
    auth = auth_module()
    assert hasattr(auth, "get_credentials"), "OAuth refresh is missing"
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    path = tmp_path / "codex-auth.json"
    fresh = auth.credentials_from_response(token_response())
    auth.save_credentials(replace(fresh, expires_at=1), path)
    calls = []
    def post(url, payload, **kwargs):
        calls.append((url, payload))
        return {**token_response(), "refresh_token": "test-rotated-not-real"}
    monkeypatch.setattr(auth, "post_json", post)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda _: auth.get_credentials(path), range(4)))
    assert len(calls) == 1
    assert calls[0][0] == "https://auth.openai.com/oauth/token"
    assert calls[0][1]["grant_type"] == "refresh_token"
    assert all(c.refresh_token == "test-rotated-not-real" for c in values)
    assert auth.load_credentials(path) == values[0]


def test_transport_retains_http_status_but_redacts_credentials(monkeypatch):
    auth = auth_module()
    assert hasattr(auth, "post_json"), "bounded OAuth transport is missing"
    import io
    from urllib.error import HTTPError
    credential = "test-access-not-real"
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://chatgpt.com/backend-api/codex/images/generations"
            assert request.get_header("User-agent") == "infinicrafter/1.0"
            body = json.dumps({"error": {"message": "quota reached " + credential}}).encode()
            raise HTTPError(request.full_url, 429, "quota", {}, io.BytesIO(body))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    with pytest.raises(auth.CodexError) as caught:
        auth.post_json("https://chatgpt.com/backend-api/codex/images/generations", {}, headers={"Authorization": "Bearer " + credential})
    assert "HTTP 429" in str(caught.value)
    assert "quota reached" in str(caught.value)
    assert credential not in str(caught.value)


def test_browser_login_exchanges_pkce_once_and_saves_only_after_callback(tmp_path, monkeypatch):
    auth = auth_module()
    assert hasattr(auth, "login"), "browser callback login is missing"
    import threading
    from urllib.request import urlopen
    from urllib.error import HTTPError
    path = tmp_path / "codex-auth.json"
    calls, threads, callback_results = [], [], []
    def post(url, payload, **kwargs):
        calls.append(payload)
        assert payload["grant_type"] == "authorization_code"
        assert payload["code"] == "test-code"
        assert len(payload["code_verifier"]) >= 43
        return token_response()
    monkeypatch.setattr(auth, "post_json", post)
    def visit(url):
        assert not path.exists()
        params = parse_qs(urlsplit(url).query)
        callback = params["redirect_uri"][0]
        def send():
            try:
                urlopen(callback + "?state=wrong&code=test-code", timeout=5)
            except HTTPError as exc:
                callback_results.append(exc.code)
            with urlopen(callback + "?state=" + params["state"][0] + "&code=test-code", timeout=5) as response:
                callback_results.append(response.status)
        thread = threading.Thread(target=send)
        threads.append(thread)
        thread.start()
    auth.login(path=path, on_url=visit, open_browser=False, port=0, timeout=10)
    for thread in threads:
        thread.join(5)
    assert callback_results == [400, 200]
    assert len(calls) == 1
    assert auth.auth_status(path)["authenticated"]


def test_authorization_code_exchange_uses_native_form_encoding(monkeypatch):
    auth = auth_module()
    import io
    class Response(io.BytesIO):
        pass
    class Opener:
        def open(self, request, timeout):
            assert request.get_header("Content-type") == "application/x-www-form-urlencoded"
            assert parse_qs(request.data.decode()) == {"code": ["test+code"], "grant_type": ["authorization_code"]}
            return Response(b'{"ok": true}')
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    assert auth.post_json(auth.TOKEN_URL, {"code": "test+code", "grant_type": "authorization_code"}, form=True) == {"ok": True}


def test_twice_escaped_unicode_credential_cannot_survive_error_or_text_output(monkeypatch):
    import io
    from email.message import Message
    from urllib.error import HTTPError
    from infini_local.services import codex_text_backend
    auth = auth_module()
    secret = "test-access-not-real"
    twice = ''.join('\\\\u%04x' % ord(ch) for ch in secret)
    assert auth._decode_unicode_runs(twice) == secret
    class Opener:
        def open(self, request, timeout):
            body = json.dumps({"error": {"message": "quota " + twice}}).encode()
            raise HTTPError(request.full_url, 403, "denied", Message(), io.BytesIO(body))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    with pytest.raises(auth.CodexError) as caught:
        auth.get_json("https://chatgpt.com/backend-api/codex/models", headers={"Authorization": "Bearer " + secret})
    assert secret not in str(caught.value).replace('\\', '')
    monkeypatch.setattr(auth, "get_credentials", lambda: auth.Credentials(secret, "test-refresh-not-real", "test-account", 9999999999))
    monkeypatch.setattr(auth, "post_sse", lambda *a, **kw: {"status": "completed", "output": [
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": '{"echo":"' + twice + '"}'}]}]})
    with pytest.raises(auth.CodexError, match="credential"):
        codex_text_backend.generate_chat({"model": "test-model", "messages": [{"role": "user", "content": "test"}]}, timeout=3)


def test_http_diagnostic_does_not_return_nested_escaped_credentials(monkeypatch):
    import io
    from email.message import Message
    from urllib.error import HTTPError
    auth = auth_module()
    secret = "test-access-not-real"
    nested = '{"token":"' + ''.join('\\u%04x' % ord(ch) for ch in secret) + '"}'
    body = json.dumps({"error": {"message": "quota " + nested}}).encode()
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 403, "denied", Message(), io.BytesIO(body))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    with pytest.raises(auth.CodexError) as caught:
        auth.get_json("https://chatgpt.com/backend-api/codex/models", headers={"Authorization": "Bearer " + secret})
    diagnostic = str(caught.value)
    assert "HTTP 403" in diagnostic
    assert secret not in diagnostic
    assert "\\u" not in diagnostic


def test_codex_http_error_keeps_non_message_diagnostic_without_secrets(monkeypatch):
    import io
    from email.message import Message
    from urllib.error import HTTPError
    auth = auth_module()
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 400, "bad", Message(), io.BytesIO(b'{"error":{"code":"unsupported_parameter","param":"stream"}}'))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    with pytest.raises(auth.CodexError, match="unsupported_parameter"):
        auth.get_json("https://chatgpt.com/backend-api/codex/models", headers={"Authorization": "Bearer test-access-not-real"})


def test_sse_rejects_late_completion_and_bounds_each_socket_read(monkeypatch):
    import io
    auth = auth_module()
    event = b'data: {"type":"response.completed","response":{"status":"completed","output":[]}}\n\n'
    socket_limits = []
    class Socket:
        def settimeout(self, value):
            socket_limits.append(value)
    class Response(io.BytesIO):
        def __init__(self):
            super().__init__(event)
            from types import SimpleNamespace
            self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=Socket()))
        def readline(self, *args, **kwargs):
            time.sleep(0.04)
            return super().readline(*args, **kwargs)
    class Opener:
        def open(self, request, timeout):
            return Response()
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    with pytest.raises(auth.CodexError, match="timed out"):
        auth.post_sse("https://chatgpt.com/backend-api/codex/responses", {"stream": True}, timeout=0.02)
    assert socket_limits and all(0 < value <= 0.02 for value in socket_limits)


def test_codex_sse_uses_completed_output_items_when_final_envelope_omits_output(monkeypatch):
    import io
    auth = auth_module()
    stream = b'data: {"type":"response.output_item.done","item":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"final"}]}}\n\ndata: {"type":"response.completed","response":{"id":"resp-2","status":"completed","output":[]}}\n\n'
    class Opener:
        def open(self, request, timeout):
            return io.BytesIO(stream)
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    result = auth.post_sse("https://chatgpt.com/backend-api/codex/responses", {"stream": True})
    assert result["output"][0]["content"][0]["text"] == "final"


def test_subscription_sse_requires_completed_event_and_never_accepts_partial_text(monkeypatch):
    import io
    auth = auth_module()
    streams = [
        b'data: {"type":"response.output_text.delta","delta":"partial"}\n\ndata: {"type":"response.completed","response":{"id":"resp-test","status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":"complete"}]}]}}\n\n',
        b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n',
    ]
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://chatgpt.com/backend-api/codex/responses"
            assert request.get_header("Accept") == "text/event-stream"
            return io.BytesIO(streams.pop(0))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    assert auth.post_sse("https://chatgpt.com/backend-api/codex/responses", {"stream": True}, headers={"Authorization": "Bearer test-access-not-real"})["id"] == "resp-test"
    with pytest.raises(auth.CodexError, match="before completion"):
        auth.post_sse("https://chatgpt.com/backend-api/codex/responses", {"stream": True})


def test_bounded_catalog_get_uses_only_codex_origin_and_redacts_errors(monkeypatch):
    import io
    from email.message import Message
    from urllib.error import HTTPError
    auth = auth_module()
    key = "test-access-not-real"
    requests = []
    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert timeout == 3
            if len(requests) == 1:
                return io.BytesIO(b'{"models": []}')
            raise HTTPError(request.full_url, 403, "denied", Message(), io.BytesIO(json.dumps({"error": {"message": "denied " + key}}).encode()))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    url = "https://chatgpt.com/backend-api/codex/models?client_version=0.4.241"
    headers = {"Authorization": "Bearer " + key}
    assert auth.get_json(url, headers=headers, timeout=3, limit=128) == {"models": []}
    assert requests[0].get_method() == "GET"
    with pytest.raises(auth.CodexError, match="HTTP 403") as caught:
        auth.get_json(url, headers=headers, timeout=3, limit=128)
    assert key not in str(caught.value)
    with pytest.raises(auth.CodexError):
        auth.get_json("https://api.openai.com/v1/models", headers=headers)


def test_native_session_roundtrip_is_private_and_status_has_no_secrets(tmp_path):
    auth = auth_module()
    path = tmp_path / "codex-auth.json"
    credentials = auth.credentials_from_response(token_response())
    auth.save_credentials(credentials, path)
    loaded = auth.load_credentials(path)
    assert loaded == credentials
    assert credentials.access_token not in repr(credentials)
    status = auth.auth_status(path)
    assert status == {"authenticated": True, "expired": False}
    assert "test-refresh" not in json.dumps(status)
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    auth.logout(path)
    assert auth.auth_status(path) == {"authenticated": False, "expired": False}
