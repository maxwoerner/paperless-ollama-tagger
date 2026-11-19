import json

import httpx
import pytest
import respx

from tagger.ollama import (OllamaBadOutput, OllamaClient, OllamaTimeout,
                           OllamaUnavailable, version_at_least)

BASE = "http://o:11434"


@pytest.fixture
def client():
    return OllamaClient(BASE, "m", 8192, 5)


def reply(content):
    return httpx.Response(200, json={"message": {"content": content}})


@respx.mock
def test_chat_sends_schema_and_parses(client):
    r = respx.post(f"{BASE}/api/chat").mock(return_value=reply('{"a": 1}'))
    schema = {"type": "object"}
    assert client.chat_json([{"role": "user", "content": "x"}], schema) == {"a": 1}
    body = json.loads(r.calls[0].request.content)
    assert body["format"] == schema and body["stream"] is False
    assert body["options"] == {"num_ctx": 8192, "temperature": 0}


@respx.mock
def test_bad_json_retries_once_then_raises(client):
    r = respx.post(f"{BASE}/api/chat").mock(return_value=reply("not json"))
    with pytest.raises(OllamaBadOutput):
        client.chat_json([], {})
    assert r.call_count == 2


@respx.mock
def test_non_object_json_is_bad(client):
    respx.post(f"{BASE}/api/chat").mock(return_value=reply("[1]"))
    with pytest.raises(OllamaBadOutput):
        client.chat_json([], {})


@respx.mock
def test_read_timeout_maps(client):
    respx.post(f"{BASE}/api/chat").mock(side_effect=httpx.ReadTimeout("t"))
    with pytest.raises(OllamaTimeout):
        client.chat_json([], {})


@respx.mock
def test_connect_error_maps(client):
    respx.post(f"{BASE}/api/chat").mock(side_effect=httpx.ConnectError("c"))
    with pytest.raises(OllamaUnavailable):
        client.chat_json([], {})


@respx.mock
def test_5xx_maps(client):
    respx.post(f"{BASE}/api/chat").mock(return_value=httpx.Response(503))
    with pytest.raises(OllamaUnavailable):
        client.chat_json([], {})


@respx.mock
def test_version(client):
    respx.get(f"{BASE}/api/version").mock(return_value=httpx.Response(200, json={"version": "0.5.7"}))
    assert client.version() == "0.5.7"


def test_version_at_least():
    assert version_at_least("0.5.0", (0, 5, 0)) is True
    assert version_at_least("0.4.9", (0, 5, 0)) is False
    assert version_at_least("0.12.1-rc1", (0, 5, 0)) is True


@respx.mock
@pytest.mark.parametrize("status", [400, 401, 404])
def test_4xx_is_unavailable_not_bad_output(client, status):
    # e.g. 404 "model not found" must abort the run, not mark every document ai-error
    respx.post(f"{BASE}/api/chat").mock(return_value=httpx.Response(status, json={"error": "model not found"}))
    with pytest.raises(OllamaUnavailable):
        client.chat_json([], {})
