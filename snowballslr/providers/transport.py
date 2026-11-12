"""HTTP transport selection for native and in-browser runtimes.

Providers talk to the network through an ``httpx.Client``. On CPython that
client uses httpx's own socket transport, unchanged from version 1. In the
browser (Pyodide) there are no sockets, so :class:`BrowserXHRTransport` carries
each request over a *synchronous* ``XMLHttpRequest``. Synchronous XHR is allowed
only inside a Web Worker, which is where the browser app runs the library; it
keeps the whole library synchronous, so the iteration loop, rate limiter, retry
policy and cache behave exactly as they do natively.

Only the transport differs. URLs, query parameters, cache keys and response
bodies are the same objects in both runtimes, which is what lets a run started
in the browser be resumed from the command line and vice versa.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

import httpx

__all__ = [
    "FORBIDDEN_REQUEST_HEADERS",
    "BrowserXHRTransport",
    "get_default_transport",
    "in_browser",
    "make_client",
    "set_default_transport",
]

# Request headers a browser refuses to let script set (Fetch standard,
# "forbidden request-header"). Setting one throws or is silently dropped
# depending on the engine, so the transport removes them up front.
FORBIDDEN_REQUEST_HEADERS = frozenset({
    "accept-charset", "accept-encoding", "access-control-request-headers",
    "access-control-request-method", "connection", "content-length", "cookie",
    "cookie2", "date", "dnt", "expect", "host", "keep-alive", "origin", "referer",
    "te", "trailer", "transfer-encoding", "upgrade", "user-agent", "via",
})

_default_transport: httpx.BaseTransport | None = None


def in_browser() -> bool:
    return sys.platform == "emscripten"


def set_default_transport(transport: httpx.BaseTransport | None) -> None:
    """Install the transport every provider client is built with."""
    global _default_transport
    _default_transport = transport


def get_default_transport() -> httpx.BaseTransport | None:
    if _default_transport is None and in_browser():  # pragma: no cover - Pyodide only
        set_default_transport(BrowserXHRTransport())
    return _default_transport


def make_client(headers: dict[str, str], timeout: float = 30.0) -> httpx.Client:
    # follow_redirects is load-bearing (see providers/base.py); browsers follow
    # redirects transparently, so the flag matters only for the native transport.
    kwargs: dict[str, Any] = {"timeout": timeout, "headers": headers, "follow_redirects": True}
    transport = get_default_transport()
    if transport is not None:
        kwargs["transport"] = transport
    return httpx.Client(**kwargs)


def _parse_header_block(block: str) -> list[tuple[str, str]]:
    out = []
    for line in block.replace("\r\n", "\n").split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            out.append((k.strip(), v.strip()))
    return out


class BrowserXHRTransport(httpx.BaseTransport):
    """httpx transport over synchronous ``XMLHttpRequest`` (Web Worker only).

    ``xhr_factory`` exists so the conversion between httpx and XHR objects can be
    tested on CPython with a stand-in; in Pyodide it defaults to
    ``js.XMLHttpRequest.new``.
    """

    def __init__(self, xhr_factory: Callable[[], Any] | None = None) -> None:
        if xhr_factory is None:  # pragma: no cover - Pyodide only
            import js  # type: ignore[import-not-found]

            xhr_factory = js.XMLHttpRequest.new
        self._new = xhr_factory

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        xhr = self._new()
        xhr.open(request.method, str(request.url), False)
        for k, v in request.headers.items():
            if k.lower() not in FORBIDDEN_REQUEST_HEADERS:
                xhr.setRequestHeader(k, v)
        body = request.read()
        try:
            xhr.send(body.decode("utf-8") if body else None)
        except Exception as exc:  # network error, CORS refusal, timeout
            raise httpx.ConnectError(f"XMLHttpRequest failed: {exc}", request=request) from exc
        status = int(xhr.status)
        if status == 0:
            # The browser reports CORS refusals and network failures as status 0
            # with no further detail available to script.
            raise httpx.ConnectError(
                "XMLHttpRequest returned status 0 (network failure or CORS refusal)",
                request=request,
            )
        text = str(xhr.responseText or "")
        headers = [(k, v) for k, v in _parse_header_block(str(xhr.getAllResponseHeaders() or ""))
                   if k.lower() not in ("content-encoding", "content-length")]
        # The browser has already decoded the body, so content-encoding and
        # content-length would describe bytes httpx never sees; drop both.
        return httpx.Response(status, headers=headers, content=text.encode("utf-8"),
                              request=request)
