"""The OpenAlex API key goes on the wire only: never into the cache, config or errors."""

import json

import httpx
import pytest

from snowballslr.determinism.cache import Cache
from snowballslr.errors import ProviderError
from snowballslr.providers import transport as tr
from snowballslr.providers.openalex import OpenAlexProvider

KEY = "oa-test-key-9f3c"


class Recorder(httpx.BaseTransport):
    def __init__(self, status=200, body=None):
        self.urls, self.status = [], status
        self.body = body if body is not None else {"id": "https://openalex.org/W1", "title": "t"}

    def handle_request(self, request):
        self.urls.append(str(request.url))
        return httpx.Response(self.status, json=self.body, request=request)


@pytest.fixture
def provider(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", KEY)
    rec = Recorder()
    tr.set_default_transport(rec)
    p = OpenAlexProvider(Cache(tmp_path / "cache"))
    yield p, rec, tmp_path
    tr.set_default_transport(None)


def test_key_sent_but_not_cached(provider):
    p, rec, tmp = provider
    p.fetch("resolve", {"select": "id", "_id": "x"}, "https://api.openalex.org/works/doi:10.1/x")
    assert f"api_key={KEY}" in rec.urls[0]
    stored = "".join(f.read_text(encoding="utf-8") for f in (tmp / "cache").rglob("*") if f.is_file())
    assert stored and KEY not in stored


def test_cache_key_independent_of_key(tmp_path, monkeypatch):
    from snowballslr.determinism.cache import cache_key
    params = {"select": "id", "_id": "x"}
    k1 = cache_key("openalex", "resolve", params)
    monkeypatch.setenv("OPENALEX_API_KEY", KEY)
    assert cache_key("openalex", "resolve", params) == k1


def test_key_redacted_in_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", KEY)
    tr.set_default_transport(Recorder(status=403, body={"message": f"bad key {KEY}"}))
    try:
        p = OpenAlexProvider(Cache(tmp_path / "cache"))
        with pytest.raises(ProviderError) as ei:
            p.fetch("resolve", {"select": "id"}, "https://api.openalex.org/works/W1")
        assert KEY not in str(ei.value) and "<redacted>" in str(ei.value)
    finally:
        tr.set_default_transport(None)


def test_no_key_no_param(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    rec = Recorder()
    tr.set_default_transport(rec)
    try:
        url = "https://api.openalex.org/works/W1"
        OpenAlexProvider(Cache(tmp_path / "c")).fetch("resolve", {"select": "id"}, url)
        assert "api_key" not in rec.urls[0]
    finally:
        tr.set_default_transport(None)


def test_config_hash_unchanged_by_environment(monkeypatch):
    from snowballslr import Config
    h = Config().config_hash
    monkeypatch.setenv("OPENALEX_API_KEY", KEY)
    assert Config().config_hash == h and KEY not in json.dumps(Config().to_dict())
