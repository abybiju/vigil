# Vigil — demo script (~6 minutes)

A tight walkthrough. Lead with the insight, show the eval (the proof), then the UI.

## 0. Setup (once)

```bash
cp .env.example .env   # add ANTHROPIC_API_KEY
make setup && make test
make seed && make eval # eval prints the headline; re-runs are free (cached)
make run               # opens the Streamlit app
```

## 1. The one-liner (15s)

> "A DTC aligner brand's support inbox is, in FDA terms, a stream of Class II device complaints. Support
> bots optimise for deflection — exactly wrong when a message is a clinical-safety event. Vigil flags
> and structures those, and proves a clinical case is never auto-answered."

Say the guardrail out loud: **"It's a detection aid with a human gate — it never makes the MDR call."**

## 2. The eval first — it's the proof (90s)

Open `eval/eval_report.md` (or the **Eval** tab).

- Point at the **headline**: *zero clinical red flags auto-answered; ~100% clinical recall; 100% MDR
  recall over the serious candidates.*
- Point at the **"dangerous misses" list** — it's empty. "Recall is the metric that matters here; a
  single false negative on a clinical flag is the failure mode, so I track the misses explicitly."
- Point at the **routing safety check**: clinical cases auto-sent = 0.
- Note the **adversarial bucket** in per-bucket recall — buried red flags, downplayed harm, sarcasm —
  caught at the same recall. "These are hand-written so the number isn't bought with strawmen."

## 3. The architecture in one breath (45s)

> "Two model passes — a structured triage call and a separate recall-tuned clinical-safety call — feed
> a **pure-Python router**. Routing is deterministic so policy can't hallucinate, and a clinical flag
> can only escalate, never clear. Rules decide refund eligibility; the LLM only phrases. Safe-lane
> replies are grounded on a cited FAQ chunk."

## 4. The UI (2–3 min)

- **Inbox** — cases sorted so clinical/MDR surface first; badges for complaint / clinical 🚩 / MDR ⚠️
  and the routing lane.
- **Case detail — a clinical case** (e.g. "one of my bottom teeth feels loose"): show the masked
  original, the structured record, the routing reason, and the **"Held for clinical review"** panel
  with the **3500A-style MDR draft**. Emphasise: *never auto-answered.*
- **Case detail — a buried red flag** (adversarial: billing question + "a back tooth feels loose"):
  the clinical-safety pass still flags it; routed to clinical review.
- **Case detail — a safe lane** (e.g. "where is my impression kit?"): show the **grounded draft** with
  the **cited source** and the human-gate caption.
- **Dashboard** — volume, complaint rate, clinical-escalation rate, auto-send rate, % replies grounded.
  "The regulatory metrics — complaint rate, clinical escalation — are what helpdesk dashboards don't
  surface."

## 5. Close (30s)

> "The capability is mature in life sciences; the *segment* is open. The edge is go-to-market —
> segment focus, native integrations, price — not secret tech. Before betting a company on it I'd
> validate buyer motivation with real customer conversations. But the hard technical claim — that a
> clinical case is never auto-answered — is proven here, not asserted."
