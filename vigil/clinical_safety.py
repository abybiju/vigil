"""The clinical-safety pass (pipeline step 3): a separate, narrow, HIGH-RECALL binary call.

This is the safety net. It is intentionally tuned to over-flag — a missed clinical red flag is
the worst possible failure. Its result is authoritative for the clinical gate in the router.
"""

from __future__ import annotations

import anthropic

from . import config
from .llm import structured_call
from .schemas import ClinicalSafety

CLINICAL_SYSTEM = """You are a clinical-safety screen for a direct-to-consumer clear-aligner brand. \
Your ONLY job is to decide whether a support message contains a potential clinical-safety red flag. \
You are a high-recall safety net — WHEN IN DOUBT, FLAG. A missed red flag is far worse than a false \
alarm. You do not diagnose; you screen.

Set clinical_red_flag = TRUE if the message mentions, even in passing, hedged, joking, minimized, or \
buried inside a billing/logistics question, ANY of these:
- pain, soreness, tenderness, an ache, or sensitivity of ANY degree — mild, moderate, or severe \
(yes, "a little sore", "mildly tender", "slight ache", "a bit sensitive" all count)
- tooth mobility, looseness, wobble, or shifting that feels wrong
- bleeding gums or mouth
- swelling of gum, jaw, face, or lip
- bite change / teeth not meeting / jaw not closing right / jaw clicking or locking
- soft-tissue injury or irritation: cut, ulcer, sore spot, rub, raw spot, laceration from a tray or edge
- allergic or reaction symptoms: rash, hives, itching, throat tightness, mouth burning, tingling
- gum recession or exposed roots
- numbness, or infection signs (pus, bad taste, fever)
- a tray that pinches, digs in, or feels tight enough to cause discomfort

Set clinical_red_flag = FALSE in ONLY two situations:
(1) there is NO bodily sensation at all — a pure logistics, shipping, billing, account, discount, or \
product-information question; OR
(2) the customer is explicitly asking you to CONFIRM that a mild early-treatment sensation is normal \
and signals it is no concern (e.g., "just confirming the day-two pressure is normal, right? no big deal").
A reported symptom that the customer merely calls "mild" or "minor" but is telling you about (not \
asking-to-confirm-normal) is still TRUE. Figures of speech with no real physical symptom — "this price \
is killing me", "my tooth will fall out if I pay this bill", "this process is a headache" — are FALSE.

When genuinely unsure, choose TRUE. List the concrete signal phrases you detected in `signals`. Set \
`confidence` to your 0-1 confidence in the TRUE/FALSE call. Return ONLY the structured tool call."""


def assess_clinical_safety(
    client: anthropic.Anthropic,
    masked_text: str,
    *,
    model: str | None = None,
) -> ClinicalSafety:
    user = f'Customer message:\n"""\n{masked_text}\n"""'
    return structured_call(
        client,
        model=model or config.CLINICAL_MODEL,
        system=CLINICAL_SYSTEM,
        user=user,
        schema_model=ClinicalSafety,
        tool_name="clinical_safety",
        max_tokens=512,
    )
