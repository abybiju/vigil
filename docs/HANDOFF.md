# Vigil — Handoff / Resume Notes

_Last updated: 2026-06-19. Read this first when resuming._

## Where we are

A working, local-first MVP. Phases 1–3 are done and unit-tested; Phase 4 (the eval) runs live; the
Streamlit UI (Phase 5) is code-complete; docs (Phase 6) are written. Only verification steps remain.

| Phase | State |
|---|---|
| 1 Foundation (schemas, db, config, ingest, packaging, rubric) | ✅ done |
| 2 Retrieval + rules | ✅ done |
| 3 Triage core (llm, triage, clinical_safety, router) | ✅ done |
| 4 Eval harness | ✅ done · v2 GREEN (clinical recall 100%, 0 auto-sent) |
| 5 Respond + Streamlit UI | ✅ done · app boots headless (HTTP 200, health ok), renders all 97 cases |
| 6 Polish + narrative | ✅ README + NARRATIVE + DEMO written · optional extras remain |

**106 unit tests pass** (`make test`) — router safety truth-table, PII no-leakage, rules, schema
cleaning, retry loop, pipeline caching, metrics, reply gating. No API needed for tests.

## Eval results — v2 is GREEN ✅ (final, 2026-06-20)

`eval/eval_report.md`, prompt `v2`, 97 messages, temperature 0:

- **Clinical red-flag recall: 100.0%** · dangerous-miss list **empty** · precision 98.1% (1 over-flag).
- **Clinical cases auto-sent: 0** ✅ (the hard safety boundary).
- Complaint detector: precision 100%, recall 93.1%, **F1 96.4%**.
- MDR-potential recall: **93.8%** (30/32). Per-bucket clinical recall: B3 100%, B4 100%, B5 (adversarial) 100%.

Known boundary cases (intentionally NOT chased — overfitting 2 ambiguous adversarial cases to a
suspiciously-perfect 100/100 is a worse interview story than an honest one):
- **Clinical FP `m026`** "aligners arrived with a cracked tray" — flagged clinical (safe direction;
  cracked tray ≈ sharp-edge hazard). Cost: held for review instead of agent_draft. Harmless.
- **MDR FN `m086`** ("hurt so bad I stopped") and **`m091`** (buried "is some gum bleeding normal?") —
  tagged clinical but not MDR. **Both still route to `clinical_review` — held for a human.** No safety
  hole: defense-in-depth means a borderline MDR call never leaks into an auto-answer.

How we got here: v1 gave clinical recall 79.2% (all 11 misses were mild non-serious B3 soreness).
Sharpened `clinical_safety.py` (flag any-degree soreness/tenderness/ache/sensitivity except the explicit
"confirm day-2 pressure is normal" decoy) + hardened `triage.py` vs downplayed/buried MDR, bumped
`PROMPT_VERSION` v1→**v2** (cache-invalidating). Re-run is free from cache: `make eval`.

Robustness fix (2026-06-20): the first overnight v2 run hung indefinitely on a stalled socket (no
client timeout). Added `REQUEST_TIMEOUT=60` + `MAX_RETRIES=3` to `get_client()` (`vigil/llm.py`,
`vigil/config.py`). Re-ran to completion.

## What's left (next session) — all optional polish; the MVP is demo-ready

1. **Your own visual UI pass:** `make run` → walk Inbox → a clinical case (held + 3500A draft) → a
   buried-red-flag adversarial case (e.g. m081/m091/m094) → a safe-lane case (grounded reply + citation)
   → Dashboard → Eval tab. (The app is verified to boot + render; this is just your eyes on the polish.)
2. **First git commit.** Nothing is committed yet (git initialized, no commits). `.env` is gitignored;
   `.env.example` has been scrubbed back to a placeholder. Safe to commit.
3. **Optional extras:** screenshots in README/DEMO; a few more adversarial messages; the optional Haiku
   pre-filter for the cost story; the optional Next.js front-end (deferred in favor of Streamlit).
4. **Rename** off the "Vigil" codename if desired (it's a placeholder per the spec).

✅ DONE this session: v2 eval green (100% clinical recall, 0 auto-sent); client timeout/retry hardening;
app boot-verified headless; `.env.example` key scrubbed; deprecation warning fixed (`width='stretch'`).

**Routing fix (caught via demo spot-check):** the router checked `clinical_red_flag` before
`potential_mdr`, so since every MDR candidate is also a clinical flag, `vigilance_review` was DEAD (0
cases) and all 30 MDR candidates fell into `clinical_review`. Reordered to **MDR-first** → vigilance
lane is the "clinical + quality" superset; both lanes are human-gated so the never-auto-answer invariant
is unchanged. Also fixed a data-integrity bug: a message that flipped from a replyable lane to a held
lane across runs kept a stale reply — `respond.ensure_reply` now deletes any reply on a held lane.
Current lane distribution: agent_draft 35 · vigilance_review 30 · clinical_review 24 · auto_send 8;
held cases carrying a reply = 0. Both fixes have tests (`test_router.py`, `test_respond.py`); 107 pass.

## How to run

```bash
make setup     # uv venv (py3.11) + deps        — once
make test      # 106 unit tests, no API
make seed      # SQLite + FAQ corpus + dataset
make eval      # full pipeline -> eval/eval_report.md (cached; make eval-fresh forces fresh)
make run       # Streamlit app
```
Requires `ANTHROPIC_API_KEY` in `.env`. **API credits live at console.anthropic.com, NOT claude.ai.**

## File map

```
vigil/llm.py          structured_call: strict tool use + Pydantic + 1 retry (+ schema cleaning)
vigil/router.py       PURE deterministic routing — the safety boundary (exhaustively tested)
vigil/triage.py       combined triage prompt (steps 1–5)
vigil/clinical_safety.py  narrow recall-tuned clinical prompt (authoritative clinical gate)
vigil/pipeline.py     process_message (cached) + persist_case + build_mdr_draft
vigil/evaluate.py     compute_metrics + load_results_frame (shared by report and UI)
vigil/respond.py      grounded safe-lane reply (rules decide, LLM phrases) + reply storage
vigil/rules.py        refund/journey eligibility (pure)
vigil/retrieve.py     TfidfRetriever (+ optional FastEmbedRetriever) over data/corpus/*.json
vigil/ingest.py       PII masking + journey resolution
vigil/schemas.py      Pydantic v2 contracts        vigil/db.py  raw-sqlite3 helper
vigil/ui.py           Streamlit badges + Altair charts      app.py  the 4-tab app
eval/rubric.md        labelling rubric (written first)
eval/build_dataset.py 97 labelled messages -> eval/dataset.csv
eval/run_eval.py      the harness -> eval/eval_report.md
migrations/001_init.sql  SQLite schema
```

Approved plan: `/Users/abybiju/.claude/plans/glowing-questing-plum.md`. Spec: `vigil_build_spec.md`.
