"""Browser transport: request/response conversion, tested on CPython with a stand-in XHR."""

import json

import httpx
import pytest

from snowballslr.providers import transport as tr


class FakeXHR:
    def __init__(self, status=200, body='{"ok": true}',
                 headers="Content-Type: application/json\r\nContent-Encoding: gzip\r\n"
                         "Content-Length: 999\r\nX-Api-Pool: polite\r\n",
                 raise_on_send=None):
        self.status, self.responseText, self._h = status, body, headers
        self.raise_on_send = raise_on_send
        self.sent_headers, self.opened, self.sent = {}, None, "unset"

    def open(self, method, url, is_async):
        self.opened = (method, url, is_async)

    def setRequestHeader(self, k, v):
        self.sent_headers[k.lower()] = v

    def send(self, body):
        if self.raise_on_send:
            raise self.raise_on_send
        self.sent = body

    def getAllResponseHeaders(self):
        return self._h


def _client(xhr):
    return httpx.Client(transport=tr.BrowserXHRTransport(xhr_factory=lambda: xhr),
                        headers={"User-Agent": "SnowBallSLR/2", "X-Custom": "1"})


def test_synchronous_get_with_query_and_json_body():
    xhr = FakeXHR()
    r = _client(xhr).get("https://api.crossref.org/works", params={"filter": "doi:10.1/x", "rows": 2})
    method, url, is_async = xhr.opened
    assert method == "GET" and is_async is False
    assert url == "https://api.crossref.org/works?filter=doi%3A10.1%2Fx&rows=2"
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert xhr.sent is None


def test_forbidden_headers_dropped_others_kept():
    xhr = FakeXHR()
    _client(xhr).get("https://api.openalex.org/works")
    assert "user-agent" not in xhr.sent_headers
    assert "accept-encoding" not in xhr.sent_headers
    assert xhr.sent_headers.get("x-custom") == "1"


def test_decoded_body_headers_removed():
    r = _client(FakeXHR()).get("https://api.openalex.org/works")
    assert "content-encoding" not in r.headers and r.headers["x-api-pool"] == "polite"
    assert r.headers["content-length"] == str(len(r.content))


def test_unicode_body_round_trips():
    body = json.dumps({"title": "Wi\u015bniewska \u2013 snowballing \u2713"}, ensure_ascii=False)
    r = _client(FakeXHR(body=body)).get("https://api.crossref.org/works/x")
    assert r.json()["title"] == "Wi\u015bniewska \u2013 snowballing \u2713"


@pytest.mark.parametrize("status", [404, 429, 503])
def test_error_statuses_are_passed_through_for_the_retry_policy(status):
    assert _client(FakeXHR(status=status, body="{}")).get("https://x.org").status_code == status


def test_status_zero_is_a_connect_error():
    with pytest.raises(httpx.ConnectError, match="CORS"):
        _client(FakeXHR(status=0, body="")).get("https://x.org")


def test_send_failure_is_a_connect_error():
    with pytest.raises(httpx.ConnectError):
        _client(FakeXHR(raise_on_send=RuntimeError("NetworkError"))).get("https://x.org")


def test_native_default_is_unchanged():
    tr.set_default_transport(None)
    assert tr.get_default_transport() is None
    c = tr.make_client({"User-Agent": "x"})
    assert not isinstance(c._transport, tr.BrowserXHRTransport)
    assert c.follow_redirects is True


def test_installed_transport_reaches_provider_clients(tmp_path):
    from snowballslr.determinism.cache import Cache
    from snowballslr.providers.crossref import CrossrefProvider

    xhr = FakeXHR(body=json.dumps({"message": {"items": []}}))
    tr.set_default_transport(tr.BrowserXHRTransport(xhr_factory=lambda: xhr))
    try:
        p = CrossrefProvider(Cache(tmp_path / "cache"))
        assert isinstance(p.client._transport, tr.BrowserXHRTransport)
    finally:
        tr.set_default_transport(None)
