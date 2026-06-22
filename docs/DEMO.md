# Vigil — Demo Talk-Track (~5 minutes)

Lead with the **insight**, show the **proof** (eval), then the **product** (live), then handle the
**"how do you connect it?"** question. You drive everything from the dashboard — no terminals.

## Setup (once, before the call)

- Open the deployed dashboard (you're signed in as the owner; it can stay private).
- The **"📨 Simulate an inbound ticket"** sidebar panel runs the real pipeline **free** on Groq
  (`VIGIL_LLM_PROVIDER=openai` + `GROQ_API_KEY` set as Streamlit secrets). No terminals, no cost.
- Locally instead: `make run` (after `make setup && make seed`).

---

## 1. The one-line insight (20s)

> "Auto-responders are a commodity. The real frame is that a DTC aligner brand's support inbox is,
> in FDA terms, a stream of **Class II medical-device complaints**. Support bots optimize for
> *deflection* — exactly the wrong instinct when a message is a clinical-safety event. Vigil flags
> and structures those, and **proves** a clinical case is never auto-answered."

Say the guardrail out loud: **"It's a detection aid with a human gate — it never makes the MDR call."**

## 2. The eval — the proof (60s)  → **Eval tab**

- Headline: **zero clinical red flags auto-answered**, clinical red-flag recall **~100%**, MDR recall
  high. Point at the **"dangerous misses" list — it's empty.**
- "Recall is the metric that matters; one missed clinical flag is the failure mode, so I track the
  misses explicitly. These numbers were measured on Claude Sonnet 4.6 — that's the documented proof."
- Point at the **adversarial bucket** in per-bucket recall: buried red flags, downplaying, sarcasm —
  caught at the same recall. "Hand-written, so the number isn't bought with strawmen."

## 3. The architecture in one breath (30s)

> "Two model passes — a structured triage call and a separate recall-tuned clinical-safety call —
> feed a **pure-Python router**. Routing is deterministic so policy can't hallucinate, and a clinical
> flag can only escalate, never clear. Rules decide refund eligibility; the LLM only phrases.
> Safe-lane replies are grounded on a cited FAQ chunk."

## 4. The product, live (90s)  → **Inbox / Case detail**, then the simulate button

- **Inbox**: cases sorted so clinical/MDR surface first; badges for complaint / clinical 🚩 / MDR ⚠️
  and the routing lane. The `source` column shows where a ticket came from (`🔌 gorgias #…`).
- **Live**: sidebar → **Simulate an inbound ticket** → pick **"Clinical — loose tooth (should be
  HELD)"** → **Triage it →**. Watch it triage and **jump to the top of the Inbox**, held.
- Open it in **Case detail**: masked message, structured complaint record, routing reason, the red
  **"Held for clinical review"** panel, and the **3500A-style MDR draft**.
- Now simulate the **"Shipping question"** preset → it routes to `auto_send` with a **grounded,
  cited reply** instead — the contrast lands the point.
- Optional kicker: the **"Buried red flag in a billing question"** preset — a billing question that
  hides "is some gum bleeding normal?" → still **held**. "The clinical-safety pass catches what a
  keyword filter would miss."

## 5. "How do you connect it with our system?" (30s)

Don't show wiring — say it:

> "It's a webhook integration — a 2-minute settings change on your side, no code. Your Gorgias (or
> Zendesk/Shopify) already fires an event on every new ticket; you point that webhook at Vigil's URL.
> We verify the HMAC signature, triage the message, and post the assessment back onto the ticket as a
> note and tags. A clinical or reportable case is held for a human and never auto-answered."

Then: "the button I just clicked runs the identical pipeline a real Gorgias webhook hits." If they
want, show `docs/INTEGRATIONS.md`.

### The picture (drop on a slide if useful)

```
   THEIR STACK                         VIGIL                          BACK TO THEM
 ┌─────────────┐   webhook POST   ┌──────────────────┐   note+tags   ┌─────────────┐
 │  Gorgias    │ ───(ticket)────▶ │ verify HMAC sig  │ ────────────▶ │ ticket gets │
 │  Zendesk    │                  │  → triage (AI)   │               │ a triage    │
 │  Shopify    │                  │  → safety router │               │ note + tags │
 └─────────────┘                  │  → human gate    │               └─────────────┘
   (2-min config,                 └────────┬─────────┘
    paste a URL)                           │ dashboard (read-only)
                                           ▼
                                  clinical case → HELD for a human, never auto-answered
```

## 6. Close (20s)

> "The capability is mature in life sciences; the *segment* — a Shopify-native brand with no
> pharmacovigilance team — is open. The edge is go-to-market: segment focus, native integrations,
> price — not secret tech. Before betting a company on it I'd validate buyer motivation with real
> customer conversations. But the hard technical claim — that a clinical case is never auto-answered —
> is **proven here, not asserted.**"

---

## Cheat sheet (the 5 things to be sure to say)

1. "Your support inbox is, in FDA terms, a stream of Class II device complaints."
2. "Detection aid with a **human gate** — never makes the authoritative MDR call."
3. "**Zero** clinical red flags auto-answered; the detector caught **~100%** — proven by the eval, not asserted."
4. "Routing is **pure Python** — the safety boundary; a clinical case can only escalate."
5. "Connecting is **pasting a webhook URL** into your helpdesk. Here's it working —" → click the button.

## If something breaks live

- Simulate button errors → it's a transient LLM hiccup; click it again (the pipeline retries) or pick
  a different preset. The dashboard's 97 pre-triaged cases + the Eval tab never need a live call.
- Have the **Eval tab** and a pre-opened **held clinical case** ready as the always-works fallback.
