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

## Signature verification (HMAC)

Each platform signs its payload with a shared secret; Vigil recomputes the HMAC over the **raw
request bytes** and compares in constant time (`vigil/webhook_security.py`) **before** parsing or
trusting anything. Real per-platform schemes:

| Platform | Header | Signature |
|---|---|---|
| Shopify | `X-Shopify-Hmac-Sha256` | `base64(HMAC-SHA256(body, secret))` |
| Zendesk | `X-Zendesk-Webhook-Signature` (+ `…-Timestamp`) | `base64(HMAC-SHA256(timestamp + body, secret))` |
| Gorgias / email / generic | `X-Vigil-Signature` | `sha256=` + `hex(HMAC-SHA256(body, secret))` |

**Posture** (set secrets via env):

```bash
VIGIL_WEBHOOK_SECRET_SHOPIFY=…      # enforces Shopify verification
VIGIL_WEBHOOK_SECRET=…              # fallback secret for all platforms
VIGIL_WEBHOOK_REQUIRE_SIGNATURE=true  # fail closed even with no secret (default: false)
```

- A secret **is** configured for the platform → signatures are **required and enforced** (a bad or
  missing signature returns `401`).
- No secret configured → verification is **skipped** (dev/demo) unless `…REQUIRE_SIGNATURE=true`.

`GET /` reports `signature_enforced` per platform so you can confirm the posture at a glance. Sending
a correctly-signed request (generic scheme):

```bash
SECRET=…; BODY=$(cat data/sample_webhooks/gorgias.json)
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | sed 's/^.* //')
curl -X POST localhost:8000/webhooks/gorgias -H 'Content-Type: application/json' \
  -H "X-Vigil-Signature: sha256=$SIG" --data "$BODY"
```

## Outbound — posting the triage back

After triage, Vigil posts back to the originating ticket/order (`vigil/outbound.py`). **The human
gate is enforced on the way out, too:** a held clinical/MDR case posts an internal alert note + tags
and **never a public reply**.

| Routing | Posted back |
|---|---|
| `clinical_review` / `vigilance_review` (held) | internal **note** (triage summary) + alert tags — *no reply* |
| `agent_draft` | note + the drafted reply as an **internal** (agent-review) note + tags |
| `auto_send` | note + grounded reply (public **only** if `VIGIL_OUTBOUND_ALLOW_AUTOSEND_PUBLIC=true`, never clinical) + tags |

Tags applied: `vigil:triaged`, `vigil:<routing>`, and conditionally `vigil:complaint`,
`vigil:clinical`, `vigil:mdr-candidate`, `vigil:held-for-review`.

**Modes** (`VIGIL_OUTBOUND_MODE`): `dry_run` (default — records the intended action to `outbound_log`
and the API response, no HTTP), `live` (calls the platform API with configured credentials), `off`.
Dry-run makes the round trip fully demoable without any real credentials. Real per-platform calls:

| Platform | Call |
|---|---|
| Zendesk | `PUT /api/v2/tickets/{id}.json` → `{ticket:{comment:{body,public}, tags}}` (Basic `email/token`) |
| Shopify | `PUT /admin/api/{ver}/orders/{id}.json` → `{order:{note, tags}}` (`X-Shopify-Access-Token`) — note + tags only |
| Gorgias | `POST /api/tickets/{id}/messages` (internal-note vs email) + `/tags` (Basic `email:api_key`) |

Email/generic have no ticket to update, so outbound is skipped for them.

## Adding a new platform

1. Write `from_<platform>(payload) -> raw_dict` in `vigil/adapters.py` (pure, tolerant of missing fields).
2. Register it in the `ADAPTERS` map.
3. Add a sample payload + a mapping test (`tests/test_adapters.py`).

No pipeline changes. For a **real** connector you'd add the platform's webhook secret verification and
(optionally) an outbound call to post the drafted reply back — left out of the MVP, which focuses on
the detection + safe-routing core.

## Production notes

- **Webhook signature verification** per platform (HMAC) — **implemented** (see above); enforced once a
  secret is configured.

Still out of MVP scope:

- **Idempotency / dedup** on platform message IDs (the MVP creates a fresh case per delivery; the
  model cache keeps re-deliveries cheap).
- **Journey enrichment from Shopify** order data (fulfillment status → journey stage) is sketched in
  `from_shopify`; a real integration would call the Shopify Admin API or join order records.
- **Outbound**: posting an approved reply back to the platform is a follow-up; today Vigil drafts and
  holds, a human sends.
