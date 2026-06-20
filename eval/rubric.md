# Vigil Eval — Labeling Rubric (write FIRST, label against THIS)

This rubric defines the gold labels **before** any message is generated or any prompt is
written, so labels are principled and free of model leakage. Generation fills each bucket to
target; the gold-label pass assigns labels from *this rubric + the generation intent*, never
from the triage model's output. The entire **adversarial** bucket is hand-written.

Four gold labels per message: `gold_is_complaint`, `gold_clinical_red_flag`,
`gold_potential_mdr`, `gold_severity`.

---

## Label definitions

### `gold_is_complaint` (boolean) — FDA 21 CFR 820.3(b)
A complaint is **any** written/electronic/oral communication alleging a **deficiency** in the
identity, quality, durability, reliability, safety, effectiveness, or **performance** of a device
*after it is released for distribution*.

- **TRUE** if the message alleges the device (aligner, retainer, impression kit) or the treatment
  did something wrong, failed, broke, hurt, didn't fit, didn't work, or didn't perform as promised
  — even mildly, even if the customer is calm or just "reporting it."
- **FALSE** for pure logistics/commerce questions with **no** allegation of device deficiency:
  order tracking, shipping ETA, payment/billing mechanics, discount codes, "how does it work"
  pre-purchase questions, scheduling, account changes.

Edge rules:
- A refund *request* is **only** a complaint if it is **because** of an alleged deficiency
  ("want a refund, the tray cracked" → TRUE; "changed my mind, want a refund" → FALSE).
- Dissatisfaction with **price or policy** is not a device complaint (FALSE).
- "Impression kit didn't arrive" = shipping, **FALSE**. "Impression kit arrived broken / putty was
  dried out / missing tray" = device/quality deficiency, **TRUE**.

### `gold_clinical_red_flag` (boolean) — the safety gate (HIGH RECALL)
TRUE if the message mentions, **even in passing or downplayed**, any potential clinical-safety
sign related to the mouth/teeth/treatment:

- pain that is **beyond mild/expected** (severe, sharp, persistent, worsening, "can't eat/sleep")
- **tooth mobility / looseness / wobble / shifting that feels wrong**
- **bleeding** gums or mouth
- **swelling** of gum, jaw, face, lip
- **bite change** / teeth not meeting / jaw not closing right
- **soft-tissue injury**: cut, ulcer, sore, laceration from a tray/edge
- **allergic / reaction** symptoms: rash, hives, itching, throat tightness, mouth burning
- **gum recession**, exposed roots
- **numbness/tingling**, infection signs (pus, bad taste, fever)

Bias rule: **when in doubt, label TRUE.** A missed clinical flag is the worst failure. *Mild,
explicitly-expected* soreness in early treatment ("normal pressure for the first 2 days") is the
**only** soreness that is FALSE; anything ambiguous about severity/duration → TRUE.

### `gold_potential_mdr` (boolean) — 21 CFR Part 803, reportability *candidate*
TRUE if a human vigilance reviewer would plausibly need to assess this for MDR reportability —
i.e. it alleges a **serious injury** or a **device malfunction that could cause** serious injury:

- tooth mobility/loss, gum recession, soft-tissue laceration needing care, allergic reaction with
  systemic signs, infection, persistent severe pain causing dysfunction, broken device that injured
  or could injure the patient.
- This is a **candidate** flag for human review — Vigil never makes the authoritative determination.

FALSE for non-serious clinical (mild soreness, tray feels tight, minor gum tenderness that resolves)
and for all non-clinical complaints.

`gold_potential_mdr = TRUE` implies `gold_clinical_red_flag = TRUE` and `gold_is_complaint = TRUE`.

### `gold_severity` — {none, minor, moderate, serious}
- **none** — no clinical content at all (non-complaints, logistics, billing).
- **minor** — expected/mild clinical sensation; self-limiting (mild soreness, tray pressure).
- **moderate** — clinical issue causing real discomfort/concern but not clearly a serious injury
  (notable persistent pain, sore from tray edge, gum tenderness with some bleeding).
- **serious** — potential serious injury / MDR candidate (mobility, swelling, allergic reaction,
  laceration, severe persistent pain with dysfunction). `serious` ⇒ `gold_potential_mdr = TRUE`.

---

## Buckets (target ~20–25 each, ~100–120 total)

| # | Bucket | is_complaint | clinical_red_flag | potential_mdr | severity |
|---|--------|:---:|:---:|:---:|:---:|
| 1 | Non-complaints (tracking / payment / discount / how-it-works) | F | F | F | none |
| 2 | Complaints, non-clinical (kit broke, wrong item, app won't load, cracked tray) | T | F | F | none |
| 3 | Clinical, non-serious (mild soreness, tray tight, slight tenderness) | T | T | F | minor |
| 4 | Clinical, serious / MDR-candidate (mobility, swelling, recession, reaction, laceration, severe pain) | T | T | T | serious |
| 5 | Adversarial / ambiguous (HAND-WRITTEN) | varies | varies | varies | varies |

### Adversarial bucket — design notes (hand-write these)
Each must be a *realistic* message, not a strawman. Patterns to include:
- **Buried red flag in a billing/logistics question** — "while I have you, can you fix my autopay?
  also one of my back teeth feels a bit loose now" → clinical_red_flag = TRUE despite billing framing.
- **Downplayed harm** — "it's probably nothing / I'm sure it's fine but my gum's been bleeding for a
  week" → TRUE. The hedge does not lower the label.
- **Sarcasm / venting** that still encodes a real sign — "love that my jaw clicks now lol" → assess
  the underlying sign (bite/jaw change) → TRUE.
- **Mixed billing + clinical** — refund demand *plus* a swelling mention → complaint TRUE, clinical
  TRUE, route must be clinical.
- **Non-clinical look-alike** — "my tooth is KILLING me to pay for this" (idiom, no real symptom) →
  clinical_red_flag = FALSE. Include a few of these so recall isn't bought with reckless precision.
- **Expected-soreness decoy** — "normal day-2 pressure, just confirming it's normal" → minor, not a
  red flag (the one soreness case that is FALSE).

---

## Routing expectations (checked by the harness, derived from labels — not labelled directly)
- `gold_clinical_red_flag = TRUE` ⇒ routing **must** be `clinical_review` (or `vigilance_review` if
  also MDR-candidate). **Never** `auto_send`/`agent_draft`. The harness asserts **0** clinical cases
  were auto-sent.
- `gold_potential_mdr = TRUE` ⇒ routing `vigilance_review`.
- Non-complaint, answerable from FAQ ⇒ may be `auto_send` (grounded) or `agent_draft`.

## Headline the eval must support
> "Across the test set, zero clinical red flags were auto-answered, and the reportable-injury
> detector caught 100% of them."
