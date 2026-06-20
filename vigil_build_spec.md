# Vigil — Build Spec v1

*Working codename "Vigil" (placeholder — rename later). A complaint & adverse-event intake layer for DTC clear-aligner support.*

---

## 0. The one-line scope

Turn an inbound DTC-aligner support message into a **structured, review-ready medical-device complaint record + a safe routing decision** — catching the messages that are legally complaints (FDA 21 CFR 820.3(b)) or potentially MDR-reportable (21 CFR Part 803), and never auto-answering a clinical-safety case.

**Framing guardrail (keep this everywhere):** Vigil is a *detection and triage aid* with a human gate. It flags and structures; a human decides reportability. It does **not** make the authoritative MDR determination. Say this out loud in the demo — it's the maturity signal.

**Demo target:** process a batch of realistic Smileie-style messages and show (a) the structured output per message, (b) the routing, (c) a metrics dashboard, (d) an eval report proving the clinical-safety recall.

---

## 1. Why this is the build (not an auto-responder)

- A "complaint" under FDA 21 CFR 820.3(b) = any written/electronic/oral communication alleging a deficiency in safety, performance, durability, etc. of a device after distribution. Most Smileie support tickets about fit/pain/breakage **are** complaints.
- Manufacturers must capture, evaluate, and (for serious injuries/malfunctions) report to FDA within 30 days (5 for urgent) → MAUDE. Misses → 483s / warning letters.
- The incumbents structurally won't own this seam: support bots optimize for *deflection*; DentalMonitoring only reads scheduled photo scans; QMS tools (Greenlight Guru, MasterControl) assume a human already keyed the complaint in. Vigil sits on the raw support firehose and bridges to the regulatory record.

---

## 2. Tech stack (matches your current toolbox)

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11 | |
| LLM | Claude API — Sonnet 4.6 for triage; Haiku 4.5 for cheap pre-filter | use tool-use / structured output for strict JSON |
| Validation | Pydantic v2 | every model output validated against a schema |
| DB | Postgres via Supabase | + `pgvector` for FAQ retrieval |
| Retrieval | Smileie public pages → chunk → embed → pgvector | FAQ, refund/return policy, how-it-works, impression guide |
| Rules engine | plain Python (no LLM) | eligibility, journey-stage, routing |
| Demo UI | Streamlit (v1, fast) | optional Next.js polish pass for the interview |
| Eval | pandas + scikit-learn metrics + markdown report | the centerpiece |

Model split rationale: a cheap Haiku pass can drop the obvious non-complaints; Sonnet does the real triage + extraction. Don't over-engineer the split for v1 — single Sonnet triage call is fine to start; add the pre-filter only if you want the cost story.

---

## 3. Data model (Postgres)

```sql
-- raw inbound, PII already masked before it hits the model
create table messages (
  id            uuid primary key default gen_random_uuid(),
  source        text,                      -- email | chat | review
  channel       text,
  received_at   timestamptz,
  customer_ref  text,                      -- masked/hashed
  order_ref     text,                      -- nullable
  journey_stage text,                      -- pre_kit | post_impression | preview_approved | in_treatment | post_treatment | unknown
  raw_text      text not null
);

-- one triage decision per message (or thread)
create table cases (
  id                 uuid primary key default gen_random_uuid(),
  message_id         uuid references messages(id),
  intent_category    text,                 -- impression_kit | payment_refund | shipping | clinical | other (multi-label ok)
  is_complaint       boolean,
  complaint_basis    text,                 -- safety | performance | durability | quality | none
  clinical_red_flag  boolean,
  severity           text,                 -- none | minor | moderate | serious
  potential_mdr      boolean,
  mdr_rationale      text,
  conf_complaint     real,
  conf_clinical      real,
  conf_mdr           real,
  routing_decision   text,                 -- auto_send | agent_draft | clinical_review | vigilance_review
  status             text default 'open',
  model_version      text,
  prompt_version     text,
  created_at         timestamptz default now()
);

-- structured extraction for the ones that ARE complaints
create table complaint_records (
  id                uuid primary key default gen_random_uuid(),
  case_id           uuid references cases(id),
  device            text,                  -- day_aligner | night_aligner | retainer | impression_kit
  issue_type        text,
  onset             text,
  duration          text,
  alleged_harm      text,
  body_site         text,                  -- tooth | gum | bite | other
  patient_narrative text,                  -- summarized, neutral
  event_date        date,
  aligner_step      text,                  -- if available
  photo_requested   boolean default false
);

-- MedWatch 3500A-style draft for MDR candidates (human reviews before anything leaves)
create table mdr_drafts (
  id                  uuid primary key default gen_random_uuid(),
  complaint_record_id uuid references complaint_records(id),
  event_type          text,               -- malfunction | injury | death
  device_problem      text,
  patient_problem     text,
  narrative           text,
  draft_status        text default 'pending_review'
);

-- everything is auditable (this is a selling point for a regulated buyer)
create table audit_log (
  id          uuid primary key default gen_random_uuid(),
  case_id     uuid references cases(id),
  actor       text,                        -- ai | human
  action      text,
  detail      jsonb,
  created_at  timestamptz default now()
);

-- gold labels for the eval harness
create table eval_labels (
  message_id            uuid references messages(id),
  gold_is_complaint     boolean,
  gold_clinical_red_flag boolean,
  gold_potential_mdr    boolean,
  gold_severity         text,
  notes                 text
);
```

---

## 4. The pipeline

```
0. Ingest & mask     -> load message, mask PII, resolve journey_stage from order_ref (rules)
1. Intent classify   -> impression_kit | payment_refund | shipping | clinical | other  (multi-label)
2. Complaint check   -> is_complaint? + complaint_basis  (the regulatory-novel classifier)
3. Clinical red-flag -> high-RECALL binary: pain, mobility, bleeding, swelling, bite change, ill-fit, reaction
4. Severity + MDR    -> severity + potential_mdr + rationale  (ALWAYS human-gated)
5. Extraction        -> fill complaint_records fields (strict JSON via tool-use)
6. Route (DETERMINISTIC, Python — not the LLM):
       clinical_red_flag                        -> clinical_review     (never auto-send)
       is_complaint & potential_mdr             -> vigilance_review    (clinical + quality)
       is_complaint & !clinical                 -> log + agent_draft
       deterministic & high retrieval-confidence-> grounded auto-draft (auto-send optional)
       else                                     -> agent_draft
7. Respond (safe lane only) -> reply grounded ONLY on retrieved FAQ chunks + cite source;
                               eligibility (refund/stage) decided by RULES, phrased by LLM
8. Persist + audit + surface on dashboard
```

Architecture choices that show judgment (call these out in the interview):
- **Two model passes, one deterministic router.** One structured "triage" call (steps 1–5) + one focused "clinical-safety" call tuned for recall (step 3, lower threshold, narrow prompt). Routing (step 6) is plain Python so policy never hallucinates.
- **Rules decide, the LLM phrases.** Refund eligibility / journey gating live in Python, not in a prompt.
- **Grounding kills policy hallucination.** Safe-lane replies cite the exact Smileie source chunk.
- **Confidence is soft; the eval harness is the proof.** Emit per-decision confidence, threshold it in the router, but trust the eval — not the model's self-reported number — for the safety claim.

---

## 5. Eval harness — the centerpiece

This is what turns a demo into a portfolio piece. Build it early; it drives prompt iteration.

**Dataset:** ~80–120 realistic messages across these buckets:
1. Clear non-complaints (tracking, payment, discount questions)
2. Clear complaints, non-clinical (impression kit broke, wrong item, app won't load)
3. Clinical, non-serious (mild soreness, tray feels tight)
4. Clinical, serious / MDR-candidate (tooth mobility, severe persistent pain, swelling, gum recession, allergic reaction)
5. **Adversarial / ambiguous** (mixed signals, downplayed harm — "it's probably fine but my tooth wiggles", sarcasm, buried red flag in a billing question)

**Gold labels:** `is_complaint`, `clinical_red_flag`, `potential_mdr`, `severity`.

**Method to avoid leakage:** write the labeling rubric FIRST, generate messages to fill each cell, then label in a separate pass (or hand-write the adversarial set). Keep the rubric in the repo.

**Metrics to report:**
- Clinical red-flag detector: **recall (primary — target ~1.0)**, precision, and an explicit list of false negatives (the dangerous misses — must be empty).
- Complaint detector: precision / recall / F1.
- MDR-potential: recall on the serious cases.
- Routing safety check: **% of clinical cases that got auto-sent = must be 0.**

**Output:** confusion matrix + a one-page `eval_report.md`. The headline line you want to be able to say: *"Across the test set, zero clinical red flags were auto-answered, and the reportable-injury detector caught 100% of them."*

---

## 6. Demo surface (Streamlit v1)

1. **Inbox** — incoming messages with triage badges (complaint / clinical / MDR-flag / routed-to).
2. **Case detail** — original message, structured complaint record, routing decision + reasoning + confidence, and either the grounded draft (with cited source) or the "held for clinical review" state; for MDR candidates, the 3500A-style draft.
3. **Dashboard** — volume, complaint rate, clinical-escalation rate, auto-send rate, time-to-first-response, % grounded-with-citation. (Same aesthetic as the helpdesk dashboards, but with the regulatory metrics those tools don't surface.)
4. **Eval tab** — the confusion matrix + recall numbers.

---

## 7. Build order (parallelizable — good for Claude Code `/plan` + `/tdd`)

- **Phase 1 — Foundation:** repo, Pydantic schemas, Postgres schema, PII masking, sample-data scaffold.
- **Phase 2 — Retrieval + rules:** scrape & embed Smileie FAQ/policy into pgvector; deterministic eligibility/journey rules.
- **Phase 3 — Triage core:** triage call + clinical-safety call + extraction + deterministic router.
- **Phase 4 — Eval (start in parallel with Phase 3):** labeled set + harness + report. TDD fits perfectly here — the eval *is* the test suite for prompt changes.
- **Phase 5 — UI:** inbox + case detail + dashboard + eval tab.
- **Phase 6 — Polish + narrative:** one-page "here's the gap and the safe way to close it" writeup + a tight demo script.

Suggested Claude Code flow: `/plan` Phases 1–2 together, `/tdd` the eval harness in Phase 4, run Phases 3 and 4 in parallel since the eval drives the prompts.

---

## 8. Interview narrative (the real deliverable)

The framing is NOT "I invented a new category." Competitor check (Section 9) showed the capability is mature in life sciences. The honest, stronger framing is **"I found the underserved segment inside a known category and built into it."**

> "Auto-responders are commodity. The real frame is that your support inbox is, in FDA terms, a stream of Class II medical-device complaints. Big life-sciences companies handle that with tools like IQVIA SmartSolve or Genpact, or they outsource it to a service like ProPharma — but every one of those assumes a pharmacovigilance department and a safety database you don't have. A Shopify-native aligner brand carries the identical obligation and none of that infrastructure. So I built a lightweight version of that capability, adapted to your support stack, with an eval that proves a clinical case never gets auto-answered."

Lead with the insight, name the incumbents (shows you mapped the landscape), then show the eval, then the UI. Bring up the "decision-support, not authority" caveat yourself.

---

## 9. Competitor check (DONE) + honest defensibility

**Finding:** the mechanism is a mature category, not a new invention.
- Pharmacovigilance AE-intake vendors (Genpact Cora PVAI, Oracle Argus / Safety One Intake, Cloudbyz, ProcessX) already do multichannel intake → extraction → seriousness assessment → human escalation.
- PV "chatbots" already cover devices, product-quality complaints with photos + lot numbers, and social/email AE triage.
- Enterprise complaint software (IQVIA SmartSolve, AssurX) does AI triage + reportability determination + electronic FDA/EU filing.
- ProPharma sells a managed service doing exactly this for consumer-health brands across e-commerce reviews, email, and call center.

**What's actually open:** the segment, not the tech. None of the above reaches a small, Shopify-native DTC-health brand with no PV department and no Argus budget. The remaining gap is a lightweight, self-serve, support-tool-native version for the DTC-health long tail.

**Defensibility = GTM, not moat.** Edge comes from segment focus, native integrations (Gorgias/Zendesk/Shopify), price, and speed — not secret tech. The real open question for a *company* (not the portfolio piece) is buyer motivation: small brands often don't buy compliance tooling until after their first FDA warning letter. Validate demand with real customer conversations before betting a company on it.

**Tailwind:** 2026 is a recognized "complaint handling → active surveillance" turning point (EUDAMED, FDA's own AI adverse-event platform plans), so timing is good.

**Other open risks:**
- Synthetic-data realism — adversarial cases must feel real, not strawmen.
- Regulatory framing — stays "aid with a human gate" throughout.
- Scraping — Smileie's public pages only, for a prototype; don't store real customer PII.

---

## 10. Execution sprint (≈6 focused days, compressible)

Sequenced so the highest-signal asset (the eval) is never the thing you run out of time for. Each day is a Claude Code session.

| Day | Goal | Output |
|---|---|---|
| 1 | Foundation | repo + Pydantic schemas + Supabase migration + PII masking util + sample-data scaffold |
| 2 | Eval dataset + retrieval | ~80–120 labeled messages (rubric first) + Smileie FAQ/policy scraped, chunked, embedded into pgvector |
| 3 | Triage core | `triage.py` (structured call) + `clinical_safety.py` (recall-tuned call) + `router.py` (deterministic) |
| 4 | Eval harness | run triage over labeled set → recall/precision/confusion matrix → `eval_report.md`; iterate prompts against it |
| 5 | Safe-lane responses | retrieval-grounded reply + citation + rules engine for refund/journey eligibility |
| 6 | UI + narrative | Streamlit inbox / case detail / dashboard / eval tab + demo script |

**If the interview is close (2-day minimum-viable cut):** Day 1 foundation + a *small* 30-message labeled set, Day 2 triage + router + eval report + a bare Streamlit case-detail view. The eval report alone, even on 30 messages, is the thing that wins. Skip retrieval, dashboard, and polish.

**Parallelization:** schemas (Day 1) and the dataset rubric (Day 2) are independent — scaffold both in one `/plan`. The eval harness is the test suite for your prompts, so build it `/tdd`-style alongside triage (Days 3–4 interleave).

---

## 11. Phase 1 starter kit

### Repo layout
```
vigil/
  schemas.py        # Pydantic models (Message, TriageResult, ComplaintRecord)
  ingest.py         # load + PII mask + journey-stage resolution
  triage.py         # structured Claude call (intent, complaint, severity, mdr, extraction)
  clinical_safety.py# narrow recall-tuned Claude call (clinical_red_flag + signals)
  router.py         # deterministic routing (NO llm) — the safety boundary
  retrieve.py       # pgvector search over Smileie FAQ/policy
  rules.py          # refund/journey eligibility (NO llm)
  respond.py        # grounded reply + citation for safe lane
  eval/
    dataset.csv     # gold-labeled messages
    rubric.md       # labeling rules (write FIRST)
    run_eval.py     # metrics + confusion matrix -> eval_report.md
  app.py            # Streamlit demo
  migrations/001_init.sql
```

### Triage output contract (what the model must return — validate with Pydantic)
```json
{
  "intent": ["impression_kit | payment_refund | shipping | clinical | other"],
  "is_complaint": true,
  "complaint_basis": "safety | performance | durability | quality | none",
  "severity": "none | minor | moderate | serious",
  "potential_mdr": false,
  "mdr_rationale": "string",
  "extraction": {
    "device": "day_aligner | night_aligner | retainer | impression_kit | null",
    "issue_type": "string",
    "onset": "string | null",
    "alleged_harm": "string | null",
    "body_site": "tooth | gum | bite | other | null",
    "patient_narrative": "neutral 1-2 sentence summary",
    "aligner_step": "string | null"
  },
  "confidence": { "complaint": 0.0, "mdr": 0.0 }
}
```
The clinical-safety pass is SEPARATE and narrow — returns only `{ "clinical_red_flag": bool, "signals": [...], "confidence": 0.0 }`, tuned for recall (lean toward flagging). The router takes the safety pass as authoritative for the clinical gate.

### Dataset rubric cells (target counts)
1. Non-complaints — tracking / payment / discount (~20)
2. Complaints, non-clinical — kit broke, wrong item, app issue (~20)
3. Clinical, non-serious — mild soreness, tray tight (~20)
4. Clinical, serious / MDR-candidate — mobility, severe pain, swelling, recession, reaction (~20)
5. Adversarial / ambiguous — buried red flag, downplayed harm, sarcasm, mixed billing+clinical (~20)

Label each: `is_complaint`, `clinical_red_flag`, `potential_mdr`, `severity`. Write the rubric before generating messages so labels are principled, and hand-write the adversarial bucket.

### First three Claude Code prompts
1. *"Scaffold the repo at this layout. Generate `schemas.py` as Pydantic v2 models for Message, TriageResult (matching this JSON contract), and ComplaintRecord. Generate `migrations/001_init.sql` from the Section 3 schema. Add `ingest.py` with a PII-masking function that redacts emails, names, phone numbers, and order IDs before text reaches any model."*
2. *"Implement `triage.py` and `clinical_safety.py` as two separate Claude calls returning validated Pydantic objects (use tool-use / structured output). Then `router.py`: a pure function implementing the Section 4 routing table — no LLM calls. The clinical-safety result is authoritative for the clinical gate."*
3. *"Implement `eval/run_eval.py`: load `dataset.csv`, run the full triage+router pipeline per row, compute recall/precision/F1 for the complaint and clinical detectors, recall for MDR, and the count of clinical cases that were auto-sent (must be 0). Write `eval_report.md` with a confusion matrix and a list of any false negatives."*
