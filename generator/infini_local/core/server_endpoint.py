"""Pure generator endpoint parsing; bind addresses are not client addresses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


def resolve_port(value: str | int | None = None) -> int:
    text = str(value).strip() if value is not None else ""
    if not text:
        return 5055
    if not text.isascii() or not text.isdecimal() or not 1 <= int(text) <= 65535:
        raise ValueError("INFINI_PORT must be an integer from 1 to 65535")
    return int(text)


@dataclass(frozen=True)
class ServerEndpoint:
    bind_host: str
    port: int

    @property
    def access_host(self) -> str:
        return {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(self.bind_host, self.bind_host)

    @property
    def base_url(self) -> str:
        host = self.access_host
        return f"http://{'[' + host + ']' if ':' in host else host}:{self.port}"


def resolve_server_endpoint(values: Mapping[str, str]) -> ServerEndpoint:
    return ServerEndpoint((values.get("INFINI_HOST") or "127.0.0.1").strip() or "127.0.0.1",
                          resolve_port(values.get("INFINI_PORT")))
