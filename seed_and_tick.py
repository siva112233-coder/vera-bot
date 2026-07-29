"""Seed all contexts and fire a tick — smoke-test against live server."""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

import time

BASE = "http://127.0.0.1:8080/v1"


def post(path, body):
    req = urllib.request.Request(
        f"{BASE}{path}",
        json.dumps(body).encode(),
        {"Content-Type": "application/json"},
    )
    for _ in range(5):
        try:
            return json.loads(urllib.request.urlopen(req).read())
        except (urllib.error.URLError, ConnectionResetError):
            time.sleep(0.5)
    return json.loads(urllib.request.urlopen(req).read())


def get(path):
    for _ in range(5):
        try:
            return json.loads(urllib.request.urlopen(f"{BASE}{path}").read())
        except (urllib.error.URLError, ConnectionResetError):
            time.sleep(0.5)
    return json.loads(urllib.request.urlopen(f"{BASE}{path}").read())


print("=== Resetting server state via /v1/teardown ===")
try:
    r = post("/teardown", {})
    print(f"  State reset: {r}")
except Exception as e:
    print(f"  Teardown skipped ({e})")

print("\n=== Loading seed data ===")
cats = {}
for s in ["dentists", "restaurants", "salons", "gyms", "pharmacies"]:
    with open(f"dataset/categories/{s}.json", encoding="utf-8") as f:
        cats[s] = json.load(f)

with open("dataset/merchants_seed.json", encoding="utf-8") as f:
    raw_m = json.load(f)
    merchants = raw_m.get("merchants", raw_m)

with open("dataset/triggers_seed.json", encoding="utf-8") as f:
    raw_t = json.load(f)
    triggers = raw_t.get("triggers", raw_t)

try:
    with open("dataset/customers_seed.json", encoding="utf-8") as f:
        raw_c = json.load(f)
        customers = raw_c.get("customers", raw_c)
except Exception:
    customers = []

print(f"  categories={len(cats)}  merchants={len(merchants)}  "
      f"triggers={len(triggers)}  customers={len(customers)}")

print("\n=== Pushing categories ===")
for slug, cat in cats.items():
    r = post("/context", {
        "scope": "category", "context_id": slug,
        "version": 1, "payload": cat,
        "delivered_at": "2026-04-26T08:00:00Z",
    })
    print(f"  {slug}: accepted={r['accepted']}")

print("\n=== Pushing merchants ===")
for m in merchants:
    mid = m["merchant_id"]
    r = post("/context", {
        "scope": "merchant", "context_id": mid,
        "version": 1, "payload": m,
        "delivered_at": "2026-04-26T08:00:00Z",
    })
    print(f"  {mid}: accepted={r['accepted']}")

print("\n=== Pushing customers ===")
for c in customers:
    cid = c["customer_id"]
    r = post("/context", {
        "scope": "customer", "context_id": cid,
        "version": 1, "payload": c,
        "delivered_at": "2026-04-26T08:00:00Z",
    })
    print(f"  {cid}: accepted={r['accepted']}")

print("\n=== Pushing triggers ===")
for t in triggers:
    tid = t["id"]
    r = post("/context", {
        "scope": "trigger", "context_id": tid,
        "version": 1, "payload": t,
        "delivered_at": "2026-04-26T08:00:00Z",
    })
    print(f"  {tid}: accepted={r['accepted']}")

print("\n=== Healthz ===")
hc = get("/healthz")
print(f"  status={hc['status']}  uptime={hc['uptime_seconds']}s")
print(f"  contexts: {hc['contexts_loaded']}")

print("\n=== Firing /v1/tick ===")
trigger_ids = [t["id"] for t in triggers]
result = post("/tick", {
    "now": "2026-04-26T08:00:00Z",
    "available_triggers": trigger_ids,
})
actions = result["actions"]
print(f"  {len(actions)} action(s) generated from {len(trigger_ids)} available trigger(s)\n")

for i, a in enumerate(actions, 1):
    print(f"--- Action {i} ---")
    print(f"  merchant_id : {a['merchant_id']}")
    print(f"  trigger_id  : {a['trigger_id']}")
    print(f"  send_as     : {a['send_as']}")
    print(f"  cta         : {a['cta']}")
    print(f"  suppression : {a['suppression_key']}")
    print(f"  body        : {a['body']}")
    print(f"  rationale   : {a['rationale']}")
    print()

print("=== Done ===")
