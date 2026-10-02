"""Narrow HTTP I/O: original endpoint only, caller-owned monotonic deadline.

No retries, provider selection, JSON conversion, logging or process-wide opener.
Blocking platform DNS resolution is outside Python's cancellable socket I/O.
"""
from __future__ import annotations

from functools import partial
import http.client
import io
import time
from urllib import request as urlrequest


class HttpDeadlineExceeded(TimeoutError):
    """The caller-owned monotonic deadline has expired."""


class HttpResponseTooLarge(ValueError):
    """The complete response would exceed the caller's byte bound."""


def remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise HttpDeadlineExceeded("HTTP logical-call deadline exceeded")
    return remaining


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _DeadlineReader(io.RawIOBase):
    """Check every socket recv, including status/header/chunk delimiter reads."""
    def __init__(self, raw, sock, deadline):
        self.raw, self.sock, self.deadline = raw, sock, deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        self.sock.settimeout(remaining_seconds(self.deadline))
        try:
            count = self.raw.readinto(buffer)
        except TimeoutError as error:
            raise HttpDeadlineExceeded("HTTP read deadline exceeded") from error
        remaining_seconds(self.deadline)
        return count

    def close(self):
        try:
            self.raw.close()
        finally:
            super().close()


class _DeadlineResponse(http.client.HTTPResponse):
    def __init__(self, sock, *args, deadline, **kwargs):
        super().__init__(sock, *args, **kwargs)
        # Wrap before begin(): checking only body read1 misses trickled headers.
        self.fp = io.BufferedReader(_DeadlineReader(self.fp.detach(), sock, deadline))


class _HTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, deadline, **kwargs):
        self.deadline = deadline
        super().__init__(*args, **kwargs)
        self.response_class = partial(_DeadlineResponse, deadline=deadline)
        create_connection = self._create_connection

        def connect_socket(address, timeout, *args, **kwargs):
            sock = create_connection(address, remaining_seconds(deadline), *args, **kwargs)
            try:
                sock.settimeout(remaining_seconds(deadline))  # TLS receives only TCP's remainder.
            except BaseException:
                sock.close()
                raise
            return sock
        self._create_connection = connect_socket

    def connect(self):
        self.timeout = remaining_seconds(self.deadline)
        super().connect()
        self.sock.settimeout(remaining_seconds(self.deadline))

    def send(self, data):
        if self.sock is None:
            self.connect()
        self.sock.settimeout(remaining_seconds(self.deadline))
        super().send(data)
        remaining_seconds(self.deadline)


class _HTTPSConnection(_HTTPConnection, http.client.HTTPSConnection):
    pass


def urlopen_no_redirect(req: urlrequest.Request, *, deadline: float):
    """Open only the original request; preserve HTTPError for ALL redirects."""
    class HTTPHandler(urlrequest.HTTPHandler):
        def http_open(self, req):
            return self.do_open(partial(_HTTPConnection, deadline=deadline), req)

    class HTTPSHandler(urlrequest.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(partial(_HTTPSConnection, deadline=deadline), req, context=self._context)

    return urlrequest.build_opener(_NoRedirect(), HTTPHandler(), HTTPSHandler()).open(
        req, timeout=remaining_seconds(deadline))


def read_with_deadline(response, *, deadline: float, max_bytes: int | None = None) -> bytes:
    """Return the complete exact body, never an adopted truncated success."""
    chunks, size = [], 0
    reader = getattr(response, "read1", None) or response.read
    while True:
        remaining_seconds(deadline)
        amount = 64 * 1024 if max_bytes is None else min(64 * 1024, max_bytes + 1 - size)
        chunk = reader(amount)
        remaining_seconds(deadline)
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if max_bytes is not None and size > max_bytes:
            raise HttpResponseTooLarge("HTTP response exceeds the caller's byte bound")
        chunks.append(chunk)
