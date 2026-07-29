"""API tests for POST /v1/tick."""
import pytest
from tests.conftest import (
    category_dentist, category_restaurant, category_gym, category_pharmacy,
    merchant_meera, merchant_pizza, merchant_powerhouse, merchant_apollo,
    trigger_research_dentist, trigger_ipl_pizza, trigger_seasonal_gym, trigger_supply_apollo,
)


async def _push_all(client, category, merchant, trigger, customer=None):
    """Helper: push all contexts then call tick."""
    category_id = category["slug"]
    merchant_id = merchant["merchant_id"]
    trigger_id = trigger["id"]

    await client.post("/v1/context", json={
        "scope": "category", "context_id": category_id, "version": 1,
        "payload": category, "delivered_at": "2026-04-26T08:00:00Z",
    })
    await client.post("/v1/context", json={
        "scope": "merchant", "context_id": merchant_id, "version": 1,
        "payload": merchant, "delivered_at": "2026-04-26T08:00:00Z",
    })
    await client.post("/v1/context", json={
        "scope": "trigger", "context_id": trigger_id, "version": 1,
        "payload": trigger, "delivered_at": "2026-04-26T08:00:00Z",
    })
    if customer:
        await client.post("/v1/context", json={
            "scope": "customer", "context_id": customer["customer_id"], "version": 1,
            "payload": customer, "delivered_at": "2026-04-26T08:00:00Z",
        })
    return trigger_id


@pytest.mark.asyncio
async def test_tick_empty_triggers_returns_empty(client):
    r = await client.post("/v1/tick", json={"now": "2026-04-26T08:00:00Z", "available_triggers": []})
    assert r.status_code == 200
    assert r.json()["actions"] == []


@pytest.mark.asyncio
async def test_tick_research_dentist_returns_action(client, category_dentist, merchant_meera, trigger_research_dentist):
    tid = await _push_all(client, category_dentist, merchant_meera, trigger_research_dentist)
    r = await client.post("/v1/tick", json={"now": "2026-04-26T08:00:00Z", "available_triggers": [tid]})
    assert r.status_code == 200
    actions = r.json()["actions"]
    assert len(actions) == 1
    action = actions[0]
    assert action["merchant_id"] == merchant_meera["merchant_id"]
    assert action["send_as"] == "vera"
    assert action["body"]
    assert action["cta"] in ("open_ended", "binary_yes_stop", "slot_choice", "confirm", "none")
    assert action["suppression_key"]


@pytest.mark.asyncio
async def test_tick_message_contains_merchant_owner_name(client, category_dentist, merchant_meera, trigger_research_dentist):
    tid = await _push_all(client, category_dentist, merchant_meera, trigger_research_dentist)
    r = await client.post("/v1/tick", json={"now": "2026-04-26T08:00:00Z", "available_triggers": [tid]})
    body = r.json()["actions"][0]["body"]
    assert "Meera" in body or "Dr." in body


@pytest.mark.asyncio
async def test_tick_suppressed_trigger_skipped(client, category_dentist, merchant_meera, trigger_research_dentist):
    tid = await _push_all(client, category_dentist, merchant_meera, trigger_research_dentist)
    # First tick consumes the suppression key
    r1 = await client.post("/v1/tick", json={"now": "2026-04-26T08:00:00Z", "available_triggers": [tid]})
    assert len(r1.json()["actions"]) == 1
    # Second tick: same trigger should be suppressed
    r2 = await client.post("/v1/tick", json={"now": "2026-04-26T08:01:00Z", "available_triggers": [tid]})
    assert len(r2.json()["actions"]) == 0


@pytest.mark.asyncio
async def test_tick_returns_deterministic_output(client, category_dentist, merchant_meera, trigger_research_dentist):
    """Two separate full-reset runs of the same tick must produce identical body."""
    results = []
    for version in (1, 2):
        await client.post("/v1/teardown")
        tid = await _push_all(client, category_dentist, merchant_meera, trigger_research_dentist)
        r = await client.post("/v1/tick", json={"now": "2026-04-26T08:00:00Z", "available_triggers": [tid]})
        results.append(r.json()["actions"][0]["body"])
    assert results[0] == results[1], "tick is not deterministic"


@pytest.mark.asyncio
async def test_tick_ipl_event_restaurant(client, category_restaurant, merchant_pizza, trigger_ipl_pizza):
    tid = await _push_all(client, category_restaurant, merchant_pizza, trigger_ipl_pizza)
    r = await client.post("/v1/tick", json={"now": "2026-04-26T08:00:00Z", "available_triggers": [tid]})
    actions = r.json()["actions"]
    assert len(actions) == 1
    assert actions[0]["cta"] == "binary_yes_stop"
    assert "match" in actions[0]["body"].lower() or "DC vs MI" in actions[0]["body"]


@pytest.mark.asyncio
async def test_tick_supply_alert_pharmacy(client, category_pharmacy, merchant_apollo, trigger_supply_apollo):
    tid = await _push_all(client, category_pharmacy, merchant_apollo, trigger_supply_apollo)
    r = await client.post("/v1/tick", json={"now": "2026-04-26T08:00:00Z", "available_triggers": [tid]})
    actions = r.json()["actions"]
    assert len(actions) == 1
    assert "atorvastatin" in actions[0]["body"].lower()


@pytest.mark.asyncio
async def test_tick_skips_missing_context(client):
    """Trigger with no matching merchant context → 0 actions (no crash)."""
    await client.post("/v1/context", json={
        "scope": "trigger", "context_id": "t_ghost", "version": 1,
        "payload": {"id": "t_ghost", "kind": "perf_dip", "scope": "merchant",
                    "merchant_id": "m_ghost_nonexistent", "urgency": 3,
                    "suppression_key": "sk_ghost", "payload": {}},
        "delivered_at": "2026-04-26T08:00:00Z",
    })
    r = await client.post("/v1/tick", json={"now": "2026-04-26T08:00:00Z", "available_triggers": ["t_ghost"]})
    assert r.status_code == 200
    assert r.json()["actions"] == []
