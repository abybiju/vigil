# Vigil

[![Live demo](https://img.shields.io/badge/Live%20demo-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://abybiju-vigil-app-gv3tkv.streamlit.app)

*Working codename — a complaint & adverse-event intake/triage layer for DTC clear-aligner support.*

**🚀 Live demo:** https://abybiju-vigil-app-gv3tkv.streamlit.app

Vigil turns an inbound support message into a **structured, review-ready medical-device complaint
record + a safe routing decision** — catching messages that are legally complaints
(FDA 21 CFR 820.3(b)) or potentially MDR-reportable (21 CFR Part 803), and **never auto-answering a
clinical-safety case**.

> **Framing guardrail (everywhere in this project):** Vigil is a *detection & triage aid with a human
> gate*. It flags and structures; a human decides reportability. It does **not** make the
> authoritative MDR determination.

## The gap it fills

A Shopify-native aligner brand's support inbox is, in FDA terms, a stream of Class II medical-device
complaints. Large life-sciences firms handle that obligation with pharmacovigilance stacks (Oracle
Argus, IQVIA SmartSolve) or outsource it (ProPharma) — all of which assume a safety department and a
safety database a DTC brand doesn't have. Support bots, meanwhile, optimise for *deflection*, which is
exactly the wrong instinct when a message is a clinical-safety event. Vigil sits on the raw support
firehose and bridges it to the regulatory record, with an eval that **proves** a clinical case is
never auto-answered. (Full story: [`docs/NARRATIVE.md`](docs/NARRATIVE.md).)

## Quickstart

```bash
cp .env.example .env        # add your ANTHROPIC_API_KEY (only required secret)
make setup                  # provision Python 3.11 venv + install deps (no torch on the default path)
make test                   # unit tests — pure safety-critical logic, no API calls
make seed                   # init local SQLite DB, embed the FAQ corpus, load the labelled dataset
make eval                   # run the eval harness over every message -> eval/eval_report.md
make run                    # launch the Streamlit demo (Inbox · Case detail · Dashboard · Eval)
```

Local-first: clone-and-run with only an Anthropic API key. SQLite for storage, in-process TF-IDF
retrieval — no external services and no model downloads on the default path. `make eval` caches every
model output, so re-running the report is free; `make eval-fresh` forces fresh calls.

**Deploy the demo:** the app reads from SQLite and makes no API calls at render time, so the hosted
demo needs no key — it ships with a bundled read-only snapshot (`demo.db`). Deploy free on
**Streamlit Community Cloud** (`app.py`, no secrets). Steps + alternatives in
[`docs/DEPLOY.md`](docs/DEPLOY.md). _(Note: Vercel can't host Streamlit — see that doc.)_

## Architecture (the judgment calls)

```
ingest+mask → triage (1 call, steps 1–5) → clinical-safety (1 narrow recall-tuned call)
            → ROUTER (pure Python — the safety boundary) → respond (safe lane only) → persist + audit
```

- **Two model passes, one deterministic router.** A combined *triage* call (intent → complaint →
  severity → MDR → extraction) plus a separate, narrow *clinical-safety* call tuned for **recall**.
  Routing is **pure Python** (`vigil/router.py`) so policy can never hallucinate — and a clinical red
  flag or potential MDR event can never reach an auto-send/agent lane. The clinical-safety pass is
  authoritative for the clinical gate.
- **Rules decide, the LLM phrases.** Refund/journey eligibility lives in `vigil/rules.py`, not a
  prompt. The safe-lane reply (`vigil/respond.py`) is grounded **only** on a retrieved FAQ chunk and
  cites it.
- **Strict structured output.** Every model output is a forced, schema-constrained tool call
  (`vigil/llm.py`) validated by Pydantic v2, with one retry that feeds the validation error back.
- **The eval is the proof.** Confidence is emitted and thresholded, but the safety claim rests on the
  eval harness (`eval/run_eval.py`), not the model's self-reported numbers.

## Project layout

```
vigil/            schemas · db · config · ingest(PII mask) · llm(structured_call) · triage ·
                  clinical_safety · router · retrieve · rules · respond · pipeline · evaluate · ui · seed
eval/             rubric.md (written first) · build_dataset.py · dataset.csv · run_eval.py · eval_report.md
data/corpus/      curated Smileie-style FAQ/policy text (committed; no live scraping)
migrations/       001_init.sql (SQLite)
tests/            pure-function tests — router truth table, PII masking, rules, metrics, retry loop
app.py            Streamlit demo
```

## Connecting a support stack (integrations)

Vigil ingests through one platform-agnostic seam, so a helpdesk connector is a thin adapter — the
triage/router/respond pipeline never changes. A FastAPI webhook service (`vigil/webhook.py`) accepts
`POST /webhooks/{platform}` for **Gorgias · Zendesk · Shopify · email · generic**, runs the live
pipeline, and writes the case to the same DB the dashboard reads.

```bash
make webhook    # uvicorn on :8000 (needs ANTHROPIC_API_KEY)
curl -X POST localhost:8000/webhooks/gorgias -H 'Content-Type: application/json' \
  --data @data/sample_webhooks/gorgias.json
```

Across the bundled samples the live pipeline routes a loose-tooth Gorgias ticket to `vigilance_review`
(held), a Zendesk "where's my kit?" to a grounded `auto_send`, and — critically — an **email with a
billing question that buries "is some gum bleeding normal?" to `clinical_review` (held)**. A
clinical/MDR case is never auto-answered, whatever platform it arrives from. Inbound payloads are
verified with **per-platform HMAC signatures** (Shopify/Zendesk/generic schemes) over the raw request
bytes before they're trusted. Details: [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md).

## The eval harness — the centerpiece

The labelling rubric ([`eval/rubric.md`](eval/rubric.md)) was written **before** any message or prompt,
so labels are principled and leak-free. The dataset (97 messages across 5 buckets, incl. a hand-written
adversarial bucket) is built by [`eval/build_dataset.py`](eval/build_dataset.py); gold labels never come
from the triage model. The harness reports, into [`eval/eval_report.md`](eval/eval_report.md):

- **Clinical red-flag detector — recall (primary, target ~100%)**, precision, and an explicit list of
  false negatives (the dangerous misses — must be empty).
- Complaint detector precision/recall/F1.
- MDR-potential recall over the serious cases.
- **Routing safety check: % of clinical cases auto-sent — must be 0.**

## Honest limitations

- **Synthetic data.** Messages are hand-authored to mirror real patterns; the adversarial bucket is
  deliberately realistic, not strawmen. No real customer PII is used or stored.
- **PII masking is regex-based** (emails, phones, order/SKU refs, URLs, long digit runs) with
  best-effort name handling — no heavy NER, to keep the project clone-and-run.
- **Decision-support, not authority.** Vigil never files anything; every draft is held for human
  review. The MDR draft is a 3500A-style *starting point*, not a determination.
- The FAQ corpus is a curated illustrative snapshot of public-style content for the prototype.

See [`docs/DEMO.md`](docs/DEMO.md) for the walkthrough script.
