# Integrations — connecting Vigil to a support stack

Vigil ingests through **one platform-agnostic seam**, so connecting any helpdesk is a thin
adapter — the triage / clinical-safety / router / respond pipeline downstream never changes.

```
Gorgias ─┐
Zendesk ─┤   adapter        ingest_message        pipeline (live)
Shopify ─┼─▶ (normalize) ─▶ (mask PII, resolve ─▶ triage + clinical-safety ─▶ router ─▶ respond
Email   ─┤   to raw dict     journey stage)        (deterministic safety gate)        + persist
Custom ──┘                                                                              │
                                                                                        ▼
                                                                          same SQLite the dashboard reads
```

## The seam

Every inbound message becomes one `raw` dict:

```python
{ "source", "channel", "customer_ref", "order_ref", "journey_stage"?, "received_at"?, "raw_text" }
```

`vigil/adapters.py` maps each platform's webhook payload to that shape. `ingest_message` then
**masks PII and hashes identifiers before anything is stored or sent to a model** — so adapters may
pass raw emails/names; nothing unmasked is persisted.

## The webhook service

`vigil/webhook.py` (FastAPI) exposes:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | liveness |
| `GET` | `/` | service info + supported platforms |
| `POST` | `/webhooks/{platform}` | ingest one message — `platform` ∈ `gorgias·zendesk·shopify·email·generic` |

On POST it runs the **live pipeline** and writes the case to the same SQLite DB the Streamlit app
reads, so it appears on the dashboard in real time. Run it:

```bash
make webhook        # uvicorn on :8000 — needs ANTHROPIC_API_KEY in .env
```

## Try it (no real accounts needed)

Sample payloads live in `data/sample_webhooks/`:

```bash
curl -X POST localhost:8000/webhooks/gorgias -H 'Content-Type: application/json' \
  --data @data/sample_webhooks/gorgias.json
```

Observed routing on the bundled samples (live pipeline):

| Platform sample | Message | Routed to |
|---|---|---|
| `gorgias.json` | "a bottom tooth feels loose" | `vigilance_review` — held (MDR candidate) |
| `zendesk.json` | "where is my impression kit?" | `auto_send` — grounded, cited reply |
| `shopify.json` | "aligners arrived with a cracked tray" | `agent_draft` — complaint, non-clinical |
| `email.json` | billing question + buried "gum bleeding" | `clinical_review` — **held; buried red flag caught** |

A clinical/MDR case is **never** auto-answered, regardless of which platform it came from — the
deterministic router is the safety boundary, not any per-integration logic.

## Adding a new platform

1. Write `from_<platform>(payload) -> raw_dict` in `vigil/adapters.py` (pure, tolerant of missing fields).
2. Register it in the `ADAPTERS` map.
3. Add a sample payload + a mapping test (`tests/test_adapters.py`).

No pipeline changes. For a **real** connector you'd add the platform's webhook secret verification and
(optionally) an outbound call to post the drafted reply back — left out of the MVP, which focuses on
the detection + safe-routing core.

## Production notes (out of MVP scope)

- **Webhook signature verification** per platform (HMAC) before trusting a payload.
- **Idempotency / dedup** on platform message IDs (the MVP creates a fresh case per delivery; the
  model cache keeps re-deliveries cheap).
- **Journey enrichment from Shopify** order data (fulfillment status → journey stage) is sketched in
  `from_shopify`; a real integration would call the Shopify Admin API or join order records.
- **Outbound**: posting an approved reply back to the platform is a follow-up; today Vigil drafts and
  holds, a human sends.
