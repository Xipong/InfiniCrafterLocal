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
