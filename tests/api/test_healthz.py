"""API tests for GET /v1/healthz."""
import pytest


@pytest.mark.asyncio
async def test_healthz_ok(client):
    r = await client.get("/v1/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert "contexts_loaded" in data
    counts = data["contexts_loaded"]
    for scope in ("category", "merchant", "customer", "trigger"):
        assert scope in counts


@pytest.mark.asyncio
async def test_healthz_context_counts_increment(client):
    # Push one merchant context
    await client.post("/v1/context", json={
        "scope": "merchant",
        "context_id": "m_001",
        "version": 1,
        "payload": {"merchant_id": "m_001"},
        "delivered_at": "2026-04-26T08:00:00Z",
    })
    r = await client.get("/v1/healthz")
    assert r.json()["contexts_loaded"]["merchant"] == 1
