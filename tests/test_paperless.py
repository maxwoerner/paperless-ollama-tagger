import httpx
import pytest
import respx

from tagger.paperless import PaperlessClient, PaperlessError, PaperlessIncompatible

BASE = "http://p:8000"


@pytest.fixture
def client():
    c = PaperlessClient(BASE, "t", 5)
    yield c
    c.close()


def page(results, next_=None):
    return httpx.Response(200, json={"count": len(results), "next": next_, "results": results})


@respx.mock
def test_vocabulary_follows_pagination(client):
    respx.get(f"{BASE}/api/tags/", params={"page": "2"}).mock(
        return_value=page([{"id": 2, "name": "b"}]))
    respx.get(f"{BASE}/api/tags/").mock(
        return_value=page([{"id": 1, "name": "a"}], f"{BASE}/api/tags/?page=2&page_size=100"))
    respx.get(f"{BASE}/api/correspondents/").mock(return_value=page([{"id": 3, "name": "Telekom"}]))
    respx.get(f"{BASE}/api/document_types/").mock(return_value=page([{"id": 4, "name": "Rechnung"}]))
    respx.get(f"{BASE}/api/custom_fields/").mock(return_value=page([
        {"id": 5, "name": "Betrag", "data_type": "monetary", "extra_data": {}},
        {"id": 6, "name": "Art", "data_type": "select",
         "extra_data": {"select_options": [{"id": "a1", "label": "Privat"}]}},
    ]))
    v = client.load_vocabulary()
    assert v.tags == {"a": 1, "b": 2}
    assert v.correspondents == {"Telekom": 3}
    assert v.custom_fields[1].select_options == [{"id": "a1", "label": "Privat"}]


@respx.mock
def test_auth_and_accept_headers(client):
    r = respx.get(f"{BASE}/api/").mock(return_value=httpx.Response(200, headers={"X-Version": "2.14.0"}, json={}))
    assert client.version() == "2.14.0"
    req = r.calls[0].request
    assert req.headers["authorization"] == "Token t"
    assert req.headers["accept"] == "application/json; version=10"


@respx.mock
def test_version_missing_raises(client):
    respx.get(f"{BASE}/api/").mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(PaperlessError):
        client.version()


@respx.mock
def test_own_user_id(client):
    respx.get(f"{BASE}/api/ui_settings/").mock(return_value=httpx.Response(200, json={"user": {"id": 7}}))
    assert client.own_user_id() == 7


@respx.mock
def test_pending_query(client):
    r = respx.get(f"{BASE}/api/documents/").mock(return_value=page([]))
    assert list(client.pending_documents(5, 10)) == []
    q = r.calls[0].request.url.params
    assert q["tags__id__all"] == "5" and q["tags__id__none"] == "10" and q["ordering"] == "added"


@respx.mock
def test_pending_requery_not_next(client):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        n = len(calls)
        if n == 1:
            return page([{"id": 1}, {"id": 2}], f"{BASE}/api/documents/?page=2")
        if n == 2:
            return page([{"id": 3}])
        return page([])

    respx.get(f"{BASE}/api/documents/").mock(side_effect=handler)
    ids = [d["id"] for d in client.pending_documents(5, 10)]
    assert ids == [1, 2, 3]
    assert all("page=2" not in c for c in calls)


@respx.mock
def test_pending_stops_when_requery_repeats(client):
    respx.get(f"{BASE}/api/documents/").mock(return_value=page([{"id": 1}], f"{BASE}/api/documents/?page=2"))
    assert [d["id"] for d in client.pending_documents(5, 10)] == [1]


@respx.mock
def test_user_edited_true_false_none(client):
    url = f"{BASE}/api/documents/1/history/"
    respx.get(url).mock(return_value=httpx.Response(200, json=[
        {"action": "create", "actor": {"id": 7}}, {"action": "update", "actor": {"id": 3}}]))
    assert client.user_edited(1, 7) is True
    respx.get(url).mock(return_value=httpx.Response(200, json=[
        {"action": "create", "actor": {"id": 3}}, {"action": "update", "actor": {"id": 7}},
        {"action": "update", "actor": None}]))
    assert client.user_edited(1, 7) is False
    respx.get(url).mock(return_value=httpx.Response(404))
    assert client.user_edited(1, 7) is None


@respx.mock
def test_ensure_tags_creates_missing_only(client):
    respx.get(f"{BASE}/api/tags/").mock(return_value=page([{"id": 9, "name": "ai-review"}]))
    post = respx.post(f"{BASE}/api/tags/").mock(
        return_value=httpx.Response(201, json={"id": 10, "name": "ai-error"}))
    assert client.ensure_tags(["ai-review", "ai-error"]) == {"ai-review": 9, "ai-error": 10}
    assert post.call_count == 1


@respx.mock
def test_patch_document(client):
    r = respx.patch(f"{BASE}/api/documents/3/").mock(return_value=httpx.Response(200, json={}))
    client.patch_document(3, {"title": "x"})
    assert r.called


@respx.mock
def test_5xx_raises(client):
    respx.get(f"{BASE}/api/documents/").mock(return_value=httpx.Response(502))
    with pytest.raises(PaperlessError):
        list(client.pending_documents(5, 10))


@respx.mock
def test_connect_error_raises(client):
    respx.get(f"{BASE}/api/").mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(PaperlessError):
        client.version()


@respx.mock
def test_negotiates_api_version_downwards(client):
    def handler(request):
        if "version=10" in request.headers["accept"]:
            return httpx.Response(406, text="invalid version")
        return httpx.Response(200, headers={"X-Version": "2.14.0"}, json={})

    respx.get(f"{BASE}/api/").mock(side_effect=handler)
    respx.get(f"{BASE}/api/ui_settings/").mock(return_value=httpx.Response(200, json={"user": {"id": 1}}))
    assert client.version() == "2.14.0"
    client.own_user_id()
    last = respx.calls.last.request
    assert last.headers["accept"] == "application/json; version=9"


@respx.mock
def test_incompatible_when_server_rejects_all_supported_versions(client):
    respx.get(f"{BASE}/api/").mock(return_value=httpx.Response(406, text="invalid version"))
    with pytest.raises(PaperlessIncompatible):
        client.version()


@respx.mock
def test_history_probe(client):
    respx.get(f"{BASE}/api/documents/").mock(return_value=page([{"id": 3}]))
    h = respx.get(f"{BASE}/api/documents/3/history/")
    h.mock(return_value=httpx.Response(200, json=[]))
    assert client.history_probe() == 200
    h.mock(return_value=httpx.Response(400, text="Audit log is disabled"))
    assert client.history_probe() == 400
    h.mock(return_value=httpx.Response(403))
    assert client.history_probe() == 403


@respx.mock
def test_history_probe_without_documents(client):
    respx.get(f"{BASE}/api/documents/").mock(return_value=page([]))
    assert client.history_probe() is None


@respx.mock
def test_user_edited_real_payload_shape(client):
    # Shape taken from paperless-ngx DocumentViewSet.history (unpaginated list;
    # action is the lowercase display name; actor is {id, username} or null).
    respx.get(f"{BASE}/api/documents/1/history/").mock(return_value=httpx.Response(200, json=[
        {"id": 3, "timestamp": "2026-11-18T10:00:00Z", "action": "update",
         "changes": {"title": ["a", "b"]}, "actor": {"id": 2, "username": "anna"}},
        {"id": 1, "timestamp": "2026-11-18T09:00:00Z", "action": "create",
         "changes": {}, "actor": None},
    ]))
    assert client.user_edited(1, 7) is True
    respx.get(f"{BASE}/api/documents/1/history/").mock(return_value=httpx.Response(200, json=[
        {"id": 3, "action": "Update", "changes": {}, "actor": {"id": 2, "username": "anna"}}]))
    assert client.user_edited(1, 7) is True  # tolerate capitalised action
