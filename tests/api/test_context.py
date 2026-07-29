"""API tests for POST /v1/context."""
import pytest


@pytest.mark.asyncio
async def test_context_accepted(client):
    r = await client.post("/v1/context", json={
        "scope": "merchant",
        "context_id": "m_001",
        "version": 1,
        "payload": {"merchant_id": "m_001", "identity": {"name": "Test Clinic"}},
        "delivered_at": "2026-04-26T08:00:00Z",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["accepted"] is True
    assert data["ack_id"] is not None
    assert data["stored_at"] is not None


@pytest.mark.asyncio
async def test_context_stale_version_rejected(client):
    await client.post("/v1/context", json={
        "scope": "merchant", "context_id": "m_001", "version": 5,
        "payload": {"v": 5}, "delivered_at": "2026-04-26T08:00:00Z",
    })
    r = await client.post("/v1/context", json={
        "scope": "merchant", "context_id": "m_001", "version": 3,
        "payload": {"v": 3}, "delivered_at": "2026-04-26T08:00:00Z",
    })
    # Spec §2.1: stale version → HTTP 409
    assert r.status_code == 409
    data = r.json()
    assert data["accepted"] is False
    assert data["reason"] == "stale_version"
    assert data["current_version"] == 5


@pytest.mark.asyncio
async def test_context_idempotent_same_version(client):
    body = {
        "scope": "category", "context_id": "dentists", "version": 1,
        "payload": {"slug": "dentists"}, "delivered_at": "2026-04-26T08:00:00Z",
    }
    r1 = await client.post("/v1/context", json=body)
    r2 = await client.post("/v1/context", json=body)
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Spec §2.1: re-posting the same version is a no-op → accepted=True (idempotent)
    assert r2.json()["accepted"] is True


@pytest.mark.asyncio
async def test_context_higher_version_accepted(client):
    await client.post("/v1/context", json={
        "scope": "merchant", "context_id": "m_001", "version": 1,
        "payload": {"v": 1}, "delivered_at": "2026-04-26T08:00:00Z",
    })
    r = await client.post("/v1/context", json={
        "scope": "merchant", "context_id": "m_001", "version": 2,
        "payload": {"v": 2}, "delivered_at": "2026-04-26T08:01:00Z",
    })
    assert r.json()["accepted"] is True


@pytest.mark.asyncio
async def test_all_four_scopes_accepted(client):
    for scope, cid in [
        ("category", "dentists"),
        ("merchant", "m_001"),
        ("customer", "c_001"),
        ("trigger", "t_001"),
    ]:
        r = await client.post("/v1/context", json={
            "scope": scope, "context_id": cid, "version": 1,
            "payload": {"test": True}, "delivered_at": "2026-04-26T08:00:00Z",
        })
        assert r.json()["accepted"] is True, f"Failed for scope {scope}"


@pytest.mark.asyncio
async def test_invalid_scope_returns_error(client):
    r = await client.post("/v1/context", json={
        "scope": "invalid_scope", "context_id": "x", "version": 1,
        "payload": {}, "delivered_at": "2026-04-26T08:00:00Z",
    })
    assert r.status_code in (400, 422)
