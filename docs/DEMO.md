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

---

# Problem-first walkthrough (the narrative version)

The script above is a beat-by-beat reference. This is the *story* — start with the company's pain,
make it a regulatory problem, reframe it as the insight, then show the solution. Words you can say,
with **[SHOW]** cues.

**Arc:** Problem (a company like Smileie) → why it's dangerous (FDA) → why no one covers it → the
insight → what Vigil does → prove it (eval) → show it live → how it connects → close.

## 1. Open on the company's reality — make it concrete (45s)
*[SHOW: the dashboard title]*

> "Take a brand like **Smileie** — direct-to-consumer clear aligners, sold through Shopify, support
> run through a helpdesk like Gorgias or Zendesk. They get a flood of support messages: 'my tray
> cracked,' 'my tooth feels loose,' 'where's my kit.' Like every DTC brand, they lean on bots and
> macros to **deflect** as many as possible — that's how support is measured.
>
> Here's the problem hiding in that inbox: **a clear aligner is an FDA Class II medical device.** Under
> FDA rules, a lot of those messages aren't support tickets — they're legally **complaints**, and some
> are **adverse events**. 'My tooth feels loose,' 'my gum is bleeding,' 'I think I'm having a reaction'
> — those are reportable safety signals. The instinct to *deflect and auto-answer* is exactly the
> wrong move, and it's a regulatory landmine."

## 2. Raise the stakes — why it's dangerous (30s)

> "Under 21 CFR 820.3(b), a complaint is any message alleging a device deficiency — fit, performance,
> safety. Manufacturers have to capture and evaluate those, and report serious injuries or
> malfunctions to the FDA within 30 days under Part 803. Miss them and you get 483s and warning
> letters. So a Shopify-native brand has the **identical obligation as a big medical-device company**
> — but none of the infrastructure. The incumbents don't cover this seam: support bots optimize for
> deflection, and the pharmacovigilance tools — Oracle Argus, IQVIA — assume you already have a safety
> department and a six-figure budget."

## 3. The insight + what Vigil is (30s)

> "So the reframe is simple but it changes everything: **your support inbox is, in FDA terms, a stream
> of Class II device complaints.** Vigil sits on that inbox and does two things a helpdesk never will:
> it turns each message into a **structured, review-ready complaint record**, and it makes a **safe
> routing decision** — where a clinical-safety case is **held for a human and never auto-answered.**
> It's a **detection and triage aid with a human gate** — it flags and structures; a human decides
> reportability. It never makes the FDA call itself."

## 4. Prove the claim before showing the UI (45s)
*[SHOW: **Eval tab**]*

> "Before I show you the product, here's why you can trust it. The whole thing lives or dies on one
> number — **did we ever auto-answer a clinical case?** *[point]* Zero. And the clinical-red-flag
> detector caught about **100%** of them — here's the list of dangerous misses, and it's **empty.**
> That's across ~100 messages including a hand-written adversarial set — buried red flags, sarcasm,
> downplayed harm. I track recall, not accuracy, because one missed safety signal is *the* failure mode."

## 5. Show it living — the moment that lands (90s)
*[SHOW: sidebar → **Simulate an inbound ticket**]*

> "Let me show you a ticket coming in. *[pick 'Clinical — loose tooth', click Triage it]* This mimics
> a Gorgias webhook — the same pipeline a real ticket hits."

*[It pops to the top of the Inbox, held. Open it in Case detail.]*

> "Vigil flagged it as a complaint, serious, an MDR candidate — and **held it for clinical review.**
> No auto-reply. It drafted the structured complaint record and a MedWatch-style draft for the human.
> *[switch presets]* Now a shipping question — *[Triage it]* — totally different: not a complaint, so
> it gets a **grounded reply citing the FAQ.** And the kicker —" *[pick the buried-red-flag preset]* "a
> billing question that buries 'is some gum bleeding normal?' — still **held.** A keyword filter misses
> that. The clinical-safety pass doesn't."

## 6. Handle "how does it connect to our system?" (30s)

> "Connecting is a **2-minute settings change on your side, no code.** Your helpdesk already fires a
> webhook on every new ticket — you point it at Vigil's URL. We verify the signature, triage it, and
> post the assessment **back onto the ticket** as a note and tags, right where your agents already
> work. The button I just clicked runs that exact pipeline."

## 7. Close — honest and confident (20s)

> "The capability is mature in life sciences; the **segment** isn't served — a Shopify-native brand
> with no safety team. The edge is go-to-market, not secret tech, and I'd validate buyer demand with
> real conversations before betting a company on it. But the hard technical claim — **a clinical case
> never gets auto-answered** — isn't asserted. It's proven, and you just watched it."

### Three things that make this land
- **Name Smileie specifically** and use *their* words ("my tooth feels loose") — concrete, not abstract.
- **Lead with the problem and the FDA stakes** before the demo — the demo means nothing until they feel the risk.
- **Show the eval *before* the UI.** Anyone can build a UI; the eval says "I'm an engineer who proves things."
