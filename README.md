# Vera — Magicpin AI Challenge

## Approach

Fully deterministic rule-based engine. **No LLM calls.** Same inputs always produce identical outputs.

### Architecture

```
POST /v1/context  →  ContextStore (thread-safe, versioned)
POST /v1/tick     →  TriggerPrioritizer → DecisionEngine → FactBag → TemplateRegistry → TickAction[]
POST /v1/reply    →  ConversationManager (auto-reply/intent/hostile detection) → compose_reply()
GET  /v1/healthz  →  Liveness + context counts
GET  /v1/metadata →  Team + model info
```

### Key Design Decisions

| Concern | Solution |
|---|---|
| Determinism | Pure rule tree + string templates; zero random calls |
| Category fit | 30+ builder functions, one per (action_type × category) pair |
| Specificity | Every message anchors on ≥1 number from merchant/category data |
| Hindi-English mix | Language flag in `identity.languages`; template branches on `"hi" in languages` |
| Auto-reply | Pattern regex + verbatim-repeat detection (same text 3× in a row) |
| Suppression | Thread-safe registry; key consumed atomically after action fires |
| Expiry | UTC-aware ISO parse; `now >= expires_at` → skip |
| Per-merchant dedup | One trigger per merchant per tick (highest urgency wins) |

### Running Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

### Running Tests

```bash
pytest tests/ -v --tb=short
```

### Environment Variables

All prefixed `VERA_`:

| Variable | Default | Description |
|---|---|---|
| `VERA_TEAM_NAME` | `Vera Engine` | Team name for `/v1/metadata` |
| `VERA_CONTACT_EMAIL` | `team@example.com` | Contact for `/v1/metadata` |
| `VERA_TEAM_MEMBERS` | `["Developer"]` | JSON list |
| `VERA_VERSION` | `1.0.0` | Bot version |
| `VERA_PORT` | `8080` | Server port |

### Deploy to Render

Push to GitHub, connect repo in Render dashboard, select `render.yaml`. Done.

Alternatively:

```bash
docker build -t vera-ai .
docker run -p 8080:8080 vera-ai
```
