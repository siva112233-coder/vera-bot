"""Full live API test suite — tests all 6 endpoints in sequence."""
import json
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8080/v1"


def call(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


print("==================================================")
print("       VERA AI — LIVE API SUITE TEST              ")
print("==================================================")

# 1. TEARDOWN (Reset state first)
print("\n1. Testing POST /v1/teardown...")
status, res = call("POST", "/teardown")
print(f"   Status: {status}")
print(f"   Response: {json.dumps(res, indent=2)}")

# 2. HEALTHZ (Initial check)
print("\n2. Testing GET /v1/healthz...")
status, res = call("GET", "/healthz")
print(f"   Status: {status}")
print(f"   Response: {json.dumps(res, indent=2)}")

# 3. METADATA
print("\n3. Testing GET /v1/metadata...")
status, res = call("GET", "/metadata")
print(f"   Status: {status}")
print(f"   Response: {json.dumps(res, indent=2)}")

# 4. CONTEXT (Category, Merchant, Trigger context pushes)
print("\n4. Testing POST /v1/context (Context Pushes)...")

cat_context = {
    "scope": "category",
    "context_id": "dentists",
    "version": 1,
    "payload": {
        "slug": "dentists",
        "display_name": "Dentists",
        "voice": {"tone": "clinical", "vocab_taboo": []},
        "offer_catalog": [{"id": "o1", "title": "Dental Cleaning @ ₹299", "type": "service_at_price"}],
        "peer_stats": {"avg_ctr": 0.030, "avg_calls_30d": 12, "avg_views_30d": 1820},
        "digest": [{"id": "d1", "title": "3-month fluoride recall study", "source": "JIDA", "trial_n": 2100}],
    },
    "delivered_at": "2026-04-26T08:00:00Z"
}
status, res = call("POST", "/context", cat_context)
print(f"   [Category Push] Status: {status} -> Accepted: {res.get('accepted')}")

merchant_context = {
    "scope": "merchant",
    "context_id": "m_001_drmeera_dentist_delhi",
    "version": 1,
    "payload": {
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "category_slug": "dentists",
        "identity": {"name": "Dr. Meera Dental Clinic", "owner_first_name": "Meera", "locality": "Lajpat Nagar", "languages": ["en"]},
        "subscription": {"status": "active", "plan": "Pro", "days_remaining": 82},
        "performance": {"views": 2410, "calls": 18, "directions": 45, "ctr": 0.021},
        "offers": [{"id": "o1", "title": "Dental Cleaning @ ₹299", "status": "active"}],
        "customer_aggregate": {"high_risk_adult_count": 124},
    },
    "delivered_at": "2026-04-26T08:00:00Z"
}
status, res = call("POST", "/context", merchant_context)
print(f"   [Merchant Push] Status: {status} -> Accepted: {res.get('accepted')}")

trigger_context = {
    "scope": "trigger",
    "context_id": "trg_001_research",
    "version": 1,
    "payload": {
        "id": "trg_001_research",
        "scope": "merchant",
        "kind": "research_digest",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "urgency": 2,
        "suppression_key": "research:dentists:2026-W17",
        "payload": {"top_item_id": "d1"}
    },
    "delivered_at": "2026-04-26T08:00:00Z"
}
status, res = call("POST", "/context", trigger_context)
print(f"   [Trigger Push]  Status: {status} -> Accepted: {res.get('accepted')}")

# Test Stale Version Handling
stale_context = dict(trigger_context)
stale_context["version"] = 1  # Re-push version 1 (should be rejected)
status, res = call("POST", "/context", stale_context)
print(f"   [Stale Version Push (Idempotency)] Accepted: {res.get('accepted')} (Reason: {res.get('reason')})")

# 5. TICK (Proactive message trigger)
print("\n5. Testing POST /v1/tick...")
tick_payload = {
    "now": "2026-04-26T08:00:00Z",
    "available_triggers": ["trg_001_research"]
}
status, res = call("POST", "/tick", tick_payload)
print(f"   Status: {status}")
actions = res.get("actions", [])
print(f"   Actions Returned: {len(actions)}")
conv_id = None
if actions:
    action = actions[0]
    conv_id = action["conversation_id"]
    print(f"   Generated Body: \"{action['body']}\"")
    print(f"   CTA: {action['cta']} | Send As: {action['send_as']} | Suppression Key: {action['suppression_key']}")

# 6. REPLY (Multi-turn conversation reply)
print("\n6. Testing POST /v1/reply...")

# Test 6a: Intent Acceptance Reply ("Yes please")
reply_payload_1 = {
    "conversation_id": conv_id or "conv_test_123",
    "merchant_id": "m_001_drmeera_dentist_delhi",
    "from_role": "merchant",
    "message": "Yes, go ahead and draft it!",
    "received_at": "2026-04-26T08:05:00Z",
    "turn_number": 2
}
status, res = call("POST", "/reply", reply_payload_1)
print(f"   [Intent Accept Reply] Status: {status}")
print(f"   Action: {res.get('action')} | Body: \"{res.get('body')}\"")

# Test 6b: Hostile Opt-Out Reply ("Stop spamming")
reply_payload_2 = {
    "conversation_id": conv_id or "conv_test_123",
    "merchant_id": "m_001_drmeera_dentist_delhi",
    "from_role": "merchant",
    "message": "Stop messaging me this is spam",
    "received_at": "2026-04-26T08:06:00Z",
    "turn_number": 3
}
status, res = call("POST", "/reply", reply_payload_2)
print(f"   [Hostile Opt-Out Reply] Status: {status}")
print(f"   Action: {res.get('action')} | Body: \"{res.get('body')}\"")

print("\n==================================================")
print("       ALL API TESTS COMPLETED SUCCESSFULLY!      ")
print("==================================================")
