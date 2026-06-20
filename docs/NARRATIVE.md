# Vigil — the gap, and the safe way to close it

*The one-pager. Lead with the insight, name the incumbents, then show the eval, then the UI.*

## The insight

Auto-responders are a commodity. The real frame is this: **a DTC clear-aligner brand's support inbox
is, in FDA terms, a stream of Class II medical-device complaints.** Under 21 CFR 820.3(b), a complaint
is *any* communication alleging a deficiency in the safety, performance, durability, or quality of a
device after distribution — which is most "my tray cracked / my tooth hurts / it doesn't fit" tickets.
Manufacturers must capture and evaluate these, and report serious injuries or malfunctions to FDA
within 30 days (5 for urgent) under 21 CFR Part 803. Misses become 483s and warning letters.

## Why the incumbents don't cover this seam

- **Support bots** (Gorgias, Zendesk AI, Intercom) optimise for *deflection* — the opposite of what a
  clinical-safety event needs.
- **Remote-monitoring** (DentalMonitoring) reads scheduled photo scans, not the raw support firehose.
- **QMS / complaint software** (Greenlight Guru, MasterControl, IQVIA SmartSolve, AssurX) assumes a
  human has already keyed the complaint into a quality system.
- **PV intake vendors & services** (Oracle Argus / Safety One Intake, Genpact, ProPharma) do exactly
  this multichannel intake → extraction → seriousness assessment → escalation — but every one assumes
  a pharmacovigilance department and a safety database a Shopify-native brand simply doesn't have.

So the **mechanism is mature; the segment is not served.** The honest framing isn't "I invented a
category" — it's **"I found the underserved segment inside a known category and built into it":** a
lightweight, support-stack-native version of PV intake for the DTC-health long tail.

## What Vigil actually does

It sits on the raw inbound message and produces two things a helpdesk never will:

1. A **structured, review-ready complaint record** (is-it-a-complaint, basis, severity, MDR-candidate,
   extracted device/issue/harm/body-site, neutral narrative) — and a **3500A-style MDR draft** for the
   serious ones.
2. A **safe routing decision** from a deterministic rule set, where a clinical-safety case is *held for
   a human*, never auto-answered — and the safe lane's replies are grounded only on cited FAQ sources.

## The maturity signal: decision-support, not authority

Vigil is a **detection aid with a human gate**. It flags and structures; a human decides reportability.
It never makes the authoritative MDR determination and never files anything. That boundary is enforced
in code — the router is pure Python and the clinical-safety pass can only *escalate*, never clear — and
it's **proven by the eval**: across the test set, zero clinical red flags were auto-answered and the
reportable-injury detector caught 100% of the candidates. (Numbers regenerate in
[`eval/eval_report.md`](../eval/eval_report.md).)

## Honest defensibility

The edge is **GTM, not moat**: segment focus, native integrations (Gorgias/Zendesk/Shopify), price, and
speed — not secret tech. The real open question for a *company* (not this portfolio piece) is buyer
motivation: small brands often don't buy compliance tooling until after their first warning letter.
That's a demand-validation question to answer with customer conversations, not code. Tailwind: 2026 is a
recognised "complaint handling → active surveillance" turning point (EUDAMED, FDA's own AI
adverse-event platform plans), so the timing is good.
