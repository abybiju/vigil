"""Presentation helpers for the Streamlit app: badges, colour maps, and Altair charts."""

from __future__ import annotations

import altair as alt
import pandas as pd

LANE_COLORS = {
    "clinical_review": "#dc2626",   # red — held for clinician
    "vigilance_review": "#7c3aed",  # purple — clinical + quality / MDR
    "agent_draft": "#2563eb",       # blue — agent will draft
    "auto_send": "#16a34a",         # green — grounded auto-answer
}

LANE_LABELS = {
    "clinical_review": "Clinical review",
    "vigilance_review": "Vigilance review",
    "agent_draft": "Agent draft",
    "auto_send": "Auto-send",
}

FLAG_COLORS = {
    "Complaint": "#d97706",
    "Clinical": "#dc2626",
    "MDR candidate": "#b91c1c",
}

SEVERITY_COLORS = {"none": "#94a3b8", "minor": "#eab308", "moderate": "#f97316", "serious": "#dc2626"}


def badge(text: str, bg: str, fg: str = "#ffffff") -> str:
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 9px;border-radius:11px;'
        f'font-size:0.72rem;font-weight:600;margin-right:5px;white-space:nowrap;">{text}</span>'
    )


def lane_badge(decision: str) -> str:
    return badge(LANE_LABELS.get(decision, decision), LANE_COLORS.get(decision, "#475569"))


def flag_badges(*, is_complaint: bool, clinical: bool, mdr: bool, severity: str | None = None) -> str:
    out: list[str] = []
    if is_complaint:
        out.append(badge("Complaint", FLAG_COLORS["Complaint"]))
    if clinical:
        out.append(badge("Clinical", FLAG_COLORS["Clinical"]))
    if mdr:
        out.append(badge("MDR candidate", FLAG_COLORS["MDR candidate"]))
    if severity and severity != "none":
        out.append(badge(severity.title(), SEVERITY_COLORS.get(severity, "#64748b")))
    return "".join(out) if out else badge("No flags", "#e2e8f0", "#475569")


def confusion_heatmap(cm: list[list[int]], title: str) -> alt.Chart:
    (tn, fp), (fn, tp) = cm
    df = pd.DataFrame(
        [
            {"Actual": "0 (no)", "Predicted": "0 (no)", "count": tn, "kind": "ok"},
            {"Actual": "0 (no)", "Predicted": "1 (yes)", "count": fp, "kind": "fp"},
            {"Actual": "1 (yes)", "Predicted": "0 (no)", "count": fn, "kind": "fn"},
            {"Actual": "1 (yes)", "Predicted": "1 (yes)", "count": tp, "kind": "ok"},
        ]
    )
    base = alt.Chart(df).encode(
        x=alt.X("Predicted:N", title="Predicted"),
        y=alt.Y("Actual:N", title="Actual"),
    )
    heat = base.mark_rect().encode(
        color=alt.Color("count:Q", scale=alt.Scale(scheme="blues"), legend=None),
        tooltip=["Actual", "Predicted", "count"],
    )
    text = base.mark_text(fontSize=18, fontWeight="bold").encode(
        text="count:Q",
        color=alt.condition("datum.count > 0 && datum.kind == 'fn'", alt.value("#dc2626"), alt.value("#0f172a")),
    )
    return (heat + text).properties(title=title, width=240, height=200)


def routing_bar(df: pd.DataFrame) -> alt.Chart:
    counts = df["routing_decision"].value_counts().rename_axis("lane").reset_index(name="count")
    counts["label"] = counts["lane"].map(LANE_LABELS).fillna(counts["lane"])
    domain = list(LANE_COLORS.keys())
    rng = [LANE_COLORS[k] for k in domain]
    return (
        alt.Chart(counts)
        .mark_bar()
        .encode(
            x=alt.X("count:Q", title="Cases"),
            y=alt.Y("label:N", title=None, sort="-x"),
            color=alt.Color("lane:N", scale=alt.Scale(domain=domain, range=rng), legend=None),
            tooltip=["label", "count"],
        )
        .properties(height=160)
    )


def severity_bar(df: pd.DataFrame) -> alt.Chart:
    order = ["none", "minor", "moderate", "serious"]
    counts = df["severity"].value_counts().rename_axis("severity").reset_index(name="count")
    rng = [SEVERITY_COLORS[s] for s in order]
    return (
        alt.Chart(counts)
        .mark_bar()
        .encode(
            x=alt.X("severity:N", sort=order, title=None),
            y=alt.Y("count:Q", title="Cases"),
            color=alt.Color("severity:N", scale=alt.Scale(domain=order, range=rng), legend=None),
            tooltip=["severity", "count"],
        )
        .properties(height=200)
    )
