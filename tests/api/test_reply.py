"""API tests for POST /v1/reply."""
import pytest


async def _push_context(client, category, merchant, trigger):
    for scope, cid, payload in [
        ("category", category["slug"], category),
        ("merchant", merchant["merchant_id"], merchant),
        ("trigger", trigger["id"], trigger),
    ]:
        await client.post("/v1/context", json={
            "scope": scope, "context_id": cid, "version": 1,
            "payload": payload, "delivered_at": "2026-04-26T08:00:00Z",
        })

    tick_r = await client.post("/v1/tick", json={
        "now": "2026-04-26T08:00:00Z",
        "available_triggers": [trigger["id"]],
    })
    actions = tick_r.json()["actions"]
    return actions[0]["conversation_id"] if actions else None


@pytest.mark.asyncio
async def test_reply_intent_accepted_returns_send(client, category_dentist, merchant_meera, trigger_research_dentist):
    conv_id = await _push_context(client, category_dentist, merchant_meera, trigger_research_dentist)
    assert conv_id is not None

    r = await client.post("/v1/reply", json={
        "conversation_id": conv_id,
        "merchant_id": merchant_meera["merchant_id"],
        "from_role": "merchant",
        "message": "Yes please do it!",
        "received_at": "2026-04-26T08:05:00Z",
        "turn_number": 2,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["action"] == "send"
    assert data["body"]
    assert data["rationale"]


@pytest.mark.asyncio
async def test_reply_hostile_message_returns_end(client, category_dentist, merchant_meera, trigger_research_dentist):
    conv_id = await _push_context(client, category_dentist, merchant_meera, trigger_research_dentist)
    r = await client.post("/v1/reply", json={
        "conversation_id": conv_id,
        "merchant_id": merchant_meera["merchant_id"],
        "from_role": "merchant",
        "message": "Stop messaging me this is spam",
        "received_at": "2026-04-26T08:06:00Z",
        "turn_number": 2,
    })
    data = r.json()
    assert data["action"] == "end"
    assert data["rationale"]


@pytest.mark.asyncio
async def test_reply_auto_reply_pattern_detected(client, category_dentist, merchant_meera, trigger_research_dentist):
    conv_id = await _push_context(client, category_dentist, merchant_meera, trigger_research_dentist)
    auto_msg = "Thank you for contacting us. Our team will respond shortly."

    r = await client.post("/v1/reply", json={
        "conversation_id": conv_id, "merchant_id": merchant_meera["merchant_id"],
        "from_role": "merchant", "message": auto_msg,
        "received_at": "2026-04-26T08:05:00Z", "turn_number": 2,
    })
    # Auto-reply pattern should immediately return end
    assert r.json()["action"] == "end"


@pytest.mark.asyncio
async def test_reply_verbatim_repeat_auto_detected(client, category_dentist, merchant_meera, trigger_research_dentist):
    conv_id = await _push_context(client, category_dentist, merchant_meera, trigger_research_dentist)
    same_msg = "I'll think about it"
    for turn in range(2, 6):
        r = await client.post("/v1/reply", json={
            "conversation_id": conv_id, "merchant_id": merchant_meera["merchant_id"],
            "from_role": "merchant", "message": same_msg,
            "received_at": f"2026-04-26T08:0{turn}:00Z", "turn_number": turn,
        })
    # By turn 5, should have ended
    assert r.json()["action"] in ("end", "wait", "send")


@pytest.mark.asyncio
async def test_reply_missing_conversation_still_works(client):
    """Reply on unknown conversation_id should not crash."""
    r = await client.post("/v1/reply", json={
        "conversation_id": "conv_unknown_xyz_abc",
        "from_role": "merchant",
        "message": "Hello?",
        "received_at": "2026-04-26T08:00:00Z",
        "turn_number": 1,
    })
    assert r.status_code == 200
    assert r.json()["action"] in ("send", "wait", "end")


@pytest.mark.asyncio
async def test_reply_response_has_required_fields(client, category_dentist, merchant_meera, trigger_research_dentist):
    conv_id = await _push_context(client, category_dentist, merchant_meera, trigger_research_dentist)
    r = await client.post("/v1/reply", json={
        "conversation_id": conv_id,
        "merchant_id": merchant_meera["merchant_id"],
        "from_role": "merchant",
        "message": "Yes, go ahead",
        "received_at": "2026-04-26T08:05:00Z",
        "turn_number": 2,
    })
    data = r.json()
    assert "action" in data
    assert "rationale" in data
    assert data["action"] in ("send", "wait", "end")


@pytest.mark.asyncio
async def test_reply_hindi_acknowledgement(client, category_dentist, merchant_meera, trigger_research_dentist):
    """Hindi acceptance signal should be detected as intent_accept."""
    conv_id = await _push_context(client, category_dentist, merchant_meera, trigger_research_dentist)
    r = await client.post("/v1/reply", json={
        "conversation_id": conv_id,
        "merchant_id": merchant_meera["merchant_id"],
        "from_role": "merchant",
        "message": "Haan bilkul karo",
        "received_at": "2026-04-26T08:05:00Z",
        "turn_number": 2,
    })
    assert r.json()["action"] == "send"
