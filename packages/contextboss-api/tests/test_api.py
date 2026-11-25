
import pytest
from contextboss import ContextManager
from contextboss_api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTEXTBOSS_API_KEYS", raising=False)
    mgr = ContextManager(str(tmp_path / "api.db"), budget=800, output_reserve=100)
    yield TestClient(create_app(mgr))
    mgr.close()


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTBOSS_API_KEYS", "topsecret, other")
    mgr = ContextManager(str(tmp_path / "api2.db"))
    yield TestClient(create_app(mgr))
    mgr.close()


class TestCRUD:
    def test_full_cycle(self, client):
        r = client.post("/v1/contexts", json={
            "content": "the api contract freezes on friday",
            "tags": ["contract"], "pinned": True, "provenance": "test",
        })
        assert r.status_code == 201
        eid = r.json()["id"]

        assert client.get(f"/v1/contexts/{eid}").json()["pinned"] is True
        hits = client.get("/v1/contexts", params={"q": "contract friday"}).json()
        assert hits[0]["id"] == eid

        r = client.patch(f"/v1/contexts/{eid}", json={"content": "updated contract text"})
        assert r.json()["version"] == 2

        info = client.get(f"/v1/contexts/{eid}/inspect").json()
        assert info["versions"] == [1, 2]

        assert client.delete(f"/v1/contexts/{eid}").json() == {"deleted": True}
        assert client.get(f"/v1/contexts/{eid}").status_code == 404
        assert client.get("/v1/contexts", params={"q": "contract"}).json() == []

    def test_404s_and_422s(self, client):
        assert client.get("/v1/contexts/nope").status_code == 404
        assert client.patch("/v1/contexts/nope", json={"content": "x"}).status_code == 404
        assert client.delete("/v1/contexts/nope").status_code == 404
        assert client.post("/v1/contexts", json={"content": "x", "tier": "bogus"}).status_code == 422


class TestAssembleCompactStats:
    def test_assemble_respects_budget(self, client):
        client.post("/v1/contexts", json={"content": "long filler " * 300})
        client.post("/v1/contexts", json={"content": "the key fact", "pinned": True})
        r = client.post("/v1/assemble", json={"budget": 400, "output_reserve": 64,
                                              "system": "sys", "task": "tsk"})
        body = r.json()
        assert body["total_tokens"] <= body["window"]
        assert "the key fact" in body["text"]
        assert body["decisions"]

    def test_compact(self, client):
        eid = client.post("/v1/contexts", json={
            "content": ". ".join(f"fact {i} about the rollout" for i in range(80))}).json()["id"]
        r = client.post(f"/v1/contexts/{eid}/compact", json={"target_tokens": 40})
        assert r.json()["tokens"] <= 40

    def test_stats(self, client):
        client.post("/v1/contexts", json={"content": "one"})
        assert client.get("/v1/stats").json()["entries"] == 1


class TestSync:
    def test_changes_cursor(self, client):
        client.post("/v1/contexts", json={"content": "first"})
        r1 = client.get("/v1/sync/changes", params={"since": 0}).json()
        assert len(r1["entries"]) == 1
        client.post("/v1/contexts", json={"content": "second"})
        r2 = client.get("/v1/sync/changes", params={"since": r1["cursor"]}).json()
        assert [e["content"] for e in r2["entries"]] == ["second"]

    def test_export_import_roundtrip(self, client):
        client.post("/v1/contexts", json={"content": "sync me", "tags": ["s"]})
        exported = client.get("/v1/sync/export").json()["entries"]
        assert len(exported) == 1
        r = client.post("/v1/sync/import", json={"entries": exported})
        assert r.json() == {"imported": 0, "skipped_existing": 1}


class TestAuth:
    def test_keys_required(self, auth_client):
        assert auth_client.get("/v1/stats").status_code == 401
        assert auth_client.get("/v1/stats", headers={
            "Authorization": "Bearer wrong"}).status_code == 403
        r = auth_client.get("/v1/stats", headers={"Authorization": "Bearer topsecret"})
        assert r.status_code == 200
        r = auth_client.get("/v1/stats", headers={"Authorization": "Bearer other"})
        assert r.status_code == 200

    def test_health_open(self, auth_client):
        assert auth_client.get("/v1/health").status_code == 200
