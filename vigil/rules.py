"""Deterministic policy rules — NO LLM. Rules decide eligibility; the LLM only phrases.

Keeping refund/journey logic here (not in a prompt) is the point: policy can't hallucinate,
and the decisions are unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .schemas import IntentCategory, JourneyStage

RefundTier = Literal["full", "partial", "none"]

# Intents that a grounded FAQ answer can safely handle when the message is NOT a complaint
# and carries no clinical content.
AUTO_ANSWERABLE_INTENTS: set[str] = {"shipping", "payment_refund", "impression_kit"}

JOURNEY_LABELS: dict[str, str] = {
    "pre_kit": "before the impression kit has been used",
    "post_impression": "impressions submitted, aligners not yet manufactured",
    "preview_approved": "treatment preview approved, aligners may be in production",
    "in_treatment": "aligners manufactured and treatment underway",
    "post_treatment": "treatment complete",
    "unknown": "journey stage unknown",
}

# (tier, eligible, reason) per journey stage. Mirrors data/corpus/refund_policy.json.
_REFUND_POLICY: dict[str, tuple[RefundTier, bool, str]] = {
    "pre_kit": ("full", True, "Before the impression kit is used — full refund within the guarantee window."),
    "post_impression": ("full", True, "Impressions submitted but aligners not yet manufactured — full refund available."),
    "preview_approved": ("partial", True, "Treatment preview approved; aligners may be in production — partial refund per policy."),
    "in_treatment": ("none", False, "Aligners manufactured and treatment underway — not refundable; eligible for remake/remediation on a quality or clinical issue."),
    "post_treatment": ("none", False, "Treatment complete — not eligible for refund."),
    "unknown": ("none", False, "Journey stage unknown — needs a manual eligibility check by an agent."),
}


@dataclass
class RefundDecision:
    eligible: bool
    tier: RefundTier
    reason: str
    needs_agent: bool = False


def refund_eligibility(journey_stage: JourneyStage | str) -> RefundDecision:
    """Deterministic refund decision from journey stage. Unknown/unrecognised defers to an agent."""
    resolved = _REFUND_POLICY.get(journey_stage)
    needs_agent = resolved is None or journey_stage == "unknown"
    tier, eligible, reason = resolved or _REFUND_POLICY["unknown"]
    return RefundDecision(eligible=eligible, tier=tier, reason=reason, needs_agent=needs_agent)


def journey_label(journey_stage: JourneyStage | str) -> str:
    return JOURNEY_LABELS.get(journey_stage, JOURNEY_LABELS["unknown"])


def is_auto_answerable(intents: list[IntentCategory] | list[str]) -> bool:
    """True if a grounded FAQ reply is appropriate: informational intent, nothing clinical."""
    if "clinical" in intents:
        return False
    return any(i in AUTO_ANSWERABLE_INTENTS for i in intents)
