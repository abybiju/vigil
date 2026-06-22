"""Vigil — Streamlit demo. Reads persisted cases (no model calls in the render path).

Run order: `make seed` then `make eval` populate the DB; then `make run` (this app).
Four tabs: Inbox · Case detail · Dashboard · Eval.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from vigil import config, db, ui
from vigil.evaluate import compute_metrics, load_results_frame
from vigil.respond import get_reply

st.set_page_config(page_title="Vigil", page_icon="🦷", layout="wide")


DEMO_DB = config.ROOT / "demo.db"


@st.cache_resource
def _conn():
    # Use the working DB if it has been seeded/evaluated; otherwise fall back to the bundled
    # read-only demo snapshot so a fresh deploy works out-of-the-box with no API key or setup.
    if config.DB_PATH.exists():
        conn = db.init_db(config.DB_PATH)
        if conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0] > 0:
            return conn
    if DEMO_DB.exists():
        return db.init_db(DEMO_DB)  # init_db ensures the schema/columns match the current code
    return db.init_db(config.DB_PATH)


def load_cases(conn) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT c.id AS case_id, c.message_id, c.intent_category, c.is_complaint, c.complaint_basis,
               c.clinical_red_flag, c.severity, c.potential_mdr, c.mdr_rationale,
               c.conf_complaint, c.conf_clinical, c.conf_mdr, c.routing_decision, c.routing_reason,
               c.created_at, m.raw_text, m.journey_stage, m.source, m.platform, m.external_id
        FROM cases c JOIN messages m ON m.id = c.message_id
        ORDER BY (m.platform IS NOT NULL) DESC, c.created_at DESC,
                 c.clinical_red_flag DESC, c.potential_mdr DESC, c.is_complaint DESC
        """
    ).fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    if not df.empty:
        for col in ["is_complaint", "clinical_red_flag", "potential_mdr"]:
            df[col] = df[col].astype(bool)
        if "platform" not in df.columns:  # older DB without the columns
            df["platform"] = None
            df["external_id"] = None
    return df


def _snippet(text: str, n: int = 70) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


SIM_PRESETS = {
    "Clinical — loose tooth (should be HELD)": "One of my bottom front teeth feels loose after this step and my gum is swollen.",
    "Buried red flag in a billing question": "Quick question about my autopay — also, is some gum bleeding normal when I brush with these in?",
    "Shipping question (safe lane, grounded reply)": "Where is my impression kit? I ordered it a few days ago.",
    "Non-complaint — discount question": "Do you offer any student or military discounts at checkout?",
    "Cracked tray (complaint, non-clinical)": "My aligners arrived with a crack in one of the trays, right out of the package.",
}


def _render_simulator(conn) -> None:
    """In-app 'send a ticket' panel so the connector can be demoed with no terminal/curl/tunnel."""
    with st.sidebar.expander("📨 Simulate an inbound ticket", expanded=False):
        st.caption("Mimics a Gorgias/Zendesk/Shopify webhook — runs the real triage pipeline.")
        if not config.ANTHROPIC_API_KEY:
            st.info("Live triage needs `ANTHROPIC_API_KEY` (run locally with `make run`, or add it as a "
                    "Streamlit secret). This hosted demo is read-only.", icon="🔑")
            return

        platform = st.selectbox("Source platform", ["gorgias", "zendesk", "shopify", "email"], key="sim_platform")
        preset = st.selectbox("Example message", list(SIM_PRESETS), key="sim_preset")
        text = st.text_area("Message", value=SIM_PRESETS[preset], key=f"sim_text_{preset}", height=90)

        if st.button("Triage it →", type="primary", width="stretch"):
            from vigil.llm import get_client
            from vigil.realtime import ingest_and_process
            from vigil.retrieve import load_retriever

            n = st.session_state.get("sim_counter", 0) + 1
            st.session_state["sim_counter"] = n
            raw = {"raw_text": text, "channel": platform, "source": "email", "external_id": f"DEMO-{1000 + n}"}
            with st.spinner("Triaging…"):
                res = ingest_and_process(conn, get_client(), raw, platform=platform, retriever=load_retriever(conn))
            st.session_state["sim_result"] = res
            st.rerun()

    if "sim_result" in st.session_state:
        r = st.session_state.pop("sim_result")
        verdict = "🚦 HELD for human review" if r["held_for_human"] else "✍️ reply drafted"
        st.sidebar.success(f"Triaged {r['platform']} #{r['external_id']} → **{ui.LANE_LABELS.get(r['routing_decision'], r['routing_decision'])}** · {verdict}")


# --------------------------------------------------------------------------- #
conn = _conn()
cases = load_cases(conn)

st.sidebar.title("🦷 Vigil")
st.sidebar.caption("Complaint & adverse-event intake for DTC clear-aligner support.")
st.sidebar.info(
    "**Detection aid with a human gate.** Vigil flags and structures; a human decides "
    "reportability. It does not make the authoritative MDR determination.",
    icon="🛡️",
)

_render_simulator(conn)

if cases.empty:
    st.title("Vigil")
    st.warning("No processed cases yet.")
    st.markdown(
        "Populate the demo first:\n\n"
        "```bash\nmake seed   # load messages + FAQ corpus\nmake eval   # triage + route every message\n```\n\n"
        "Then refresh this page."
    )
    st.stop()

# Sidebar case selector — the single selection control, shared across tabs.
options = cases["message_id"].tolist()


def _picker_label(r) -> str:
    tag = f"🔌 {r.platform} #{r.external_id}" if getattr(r, "platform", None) else r.message_id
    return f"{tag} · {_snippet(r.raw_text, 44)}"


labels = {r.message_id: _picker_label(r) for r in cases.itertuples()}
selected_id = st.sidebar.selectbox(
    "Open a case", options, format_func=lambda mid: labels.get(mid, mid), key="selected_case"
)

tab_inbox, tab_detail, tab_dash, tab_eval = st.tabs(["📥 Inbox", "🔎 Case detail", "📊 Dashboard", "✅ Eval"])

# --------------------------------------------------------------------------- #
# Inbox
# --------------------------------------------------------------------------- #
with tab_inbox:
    st.subheader("Inbox")
    st.caption("Sorted so clinical and MDR-candidate cases surface first. Open a case from the sidebar.")

    lanes = st.multiselect(
        "Filter by routing lane",
        options=list(ui.LANE_LABELS.keys()),
        default=list(ui.LANE_LABELS.keys()),
        format_func=lambda x: ui.LANE_LABELS[x],
    )
    view = cases[cases["routing_decision"].isin(lanes)]

    def _source(row) -> str:
        if row.get("platform"):
            ext = f" #{row['external_id']}" if row.get("external_id") else ""
            return f"🔌 {row['platform']}{ext}"
        return "sample"

    table = pd.DataFrame(
        {
            "source": [_source(r) for _, r in view.iterrows()],
            "lane": view["routing_decision"].map(ui.LANE_LABELS),
            "complaint": view["is_complaint"].map({True: "●", False: ""}),
            "clinical": view["clinical_red_flag"].map({True: "🚩", False: ""}),
            "MDR": view["potential_mdr"].map({True: "⚠️", False: ""}),
            "severity": view["severity"],
            "message": view["raw_text"].map(lambda t: _snippet(t, 90)),
        }
    )
    st.dataframe(table, hide_index=True, width="stretch", height=460)
    st.caption(f"{len(view)} of {len(cases)} cases shown. Live webhook tickets (🔌) sort to the top.")

# --------------------------------------------------------------------------- #
# Case detail
# --------------------------------------------------------------------------- #
with tab_detail:
    row = cases[cases["message_id"] == selected_id].iloc[0]
    st.subheader(f"Case {row.message_id}")
    st.markdown(
        ui.flag_badges(
            is_complaint=row.is_complaint, clinical=row.clinical_red_flag,
            mdr=row.potential_mdr, severity=row.severity,
        )
        + ui.lane_badge(row.routing_decision),
        unsafe_allow_html=True,
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**Original message** (PII masked)")
        st.info(row.raw_text)
        st.caption(f"Source: {row.source or 'email'} · journey stage: {row.journey_stage or 'unknown'}")

        st.markdown("**Routing decision**")
        st.markdown(ui.lane_badge(row.routing_decision), unsafe_allow_html=True)
        st.write(row.routing_reason)
        c1, c2, c3 = st.columns(3)
        c1.metric("Complaint conf.", f"{(row.conf_complaint or 0):.2f}")
        c2.metric("Clinical conf.", f"{(row.conf_clinical or 0):.2f}")
        c3.metric("MDR conf.", f"{(row.conf_mdr or 0):.2f}")

    with right:
        st.markdown("**Structured complaint record**")
        cr = conn.execute(
            "SELECT * FROM complaint_records WHERE case_id = ?", (row.case_id,)
        ).fetchone()
        if cr is None:
            st.caption("Not a complaint — no structured record.")
        else:
            crd = dict(cr)
            try:
                intents = ", ".join(json.loads(row.intent_category)) if row.intent_category else ""
            except (json.JSONDecodeError, TypeError):
                intents = row.intent_category or ""
            st.json(
                {
                    "intent": intents,
                    "complaint_basis": row.complaint_basis,
                    "device": crd.get("device"),
                    "issue_type": crd.get("issue_type"),
                    "alleged_harm": crd.get("alleged_harm"),
                    "body_site": crd.get("body_site"),
                    "onset": crd.get("onset"),
                    "patient_narrative": crd.get("patient_narrative"),
                }
            )

    st.divider()

    # Held-for-review vs grounded draft.
    if row.routing_decision in ("clinical_review", "vigilance_review"):
        st.error(
            f"**Held for {'clinical' if row.routing_decision == 'clinical_review' else 'vigilance (clinical + quality)'} review.** "
            "A clinical-safety case is never auto-answered.",
            icon="🚦",
        )
        if row.potential_mdr:
            mdr = conn.execute(
                """SELECT d.* FROM mdr_drafts d JOIN complaint_records r ON r.id = d.complaint_record_id
                   WHERE r.case_id = ?""",
                (row.case_id,),
            ).fetchone()
            if mdr:
                m = dict(mdr)
                st.markdown("**MedWatch 3500A-style draft** (pending human review)")
                with st.container(border=True):
                    st.write(f"**Event type:** {m['event_type']}")
                    st.write(f"**Device problem:** {m['device_problem']}")
                    st.write(f"**Patient problem:** {m['patient_problem']}")
                    st.write(f"**Narrative:** {m['narrative']}")
    else:
        reply = get_reply(conn, row.message_id)
        st.markdown("**Drafted reply** " + ("(grounded auto-send)" if row.routing_decision == "auto_send" else "(for agent review)"))
        if reply is None:
            st.caption("No draft stored.")
        else:
            with st.container(border=True):
                st.write(reply.body)
            if reply.grounded and reply.source_title:
                st.caption(f"📎 Grounded on: {reply.source_title} — {reply.source_url or ''}")
            else:
                st.caption("Not grounded on a source — handed to an agent.")

# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
with tab_dash:
    st.subheader("Operational dashboard")
    n = len(cases)
    complaint_rate = cases["is_complaint"].mean()
    clinical_rate = cases["routing_decision"].isin(["clinical_review", "vigilance_review"]).mean()
    autosend_rate = (cases["routing_decision"] == "auto_send").mean()

    rep = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(grounded),0) AS g FROM replies").fetchone()
    grounded_pct = (rep["g"] / rep["n"]) if rep["n"] else 0.0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Volume", n)
    m2.metric("Complaint rate", f"{complaint_rate * 100:.0f}%")
    m3.metric("Clinical escalation", f"{clinical_rate * 100:.0f}%")
    m4.metric("Auto-send rate", f"{autosend_rate * 100:.0f}%")
    m5.metric("Replies grounded", f"{grounded_pct * 100:.0f}%")

    st.caption("The regulatory metrics — complaint rate and clinical-escalation rate — are what helpdesk dashboards don't surface.")
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Routing distribution**")
        st.altair_chart(ui.routing_bar(cases), width="stretch")
    with c2:
        st.markdown("**Severity distribution**")
        st.altair_chart(ui.severity_bar(cases), width="stretch")

# --------------------------------------------------------------------------- #
# Eval
# --------------------------------------------------------------------------- #
with tab_eval:
    st.subheader("Evaluation — the proof")
    try:
        metrics = compute_metrics(load_results_frame(conn))
    except ValueError:
        st.info("No gold-labelled results yet. Run `make eval`.")
        st.stop()

    safe = not metrics.clinical_false_negatives and metrics.clinical_auto_sent == 0
    headline = (
        f"Across {metrics.n} messages, **{metrics.clinical_auto_sent}** clinical red flags were "
        f"auto-answered, and the clinical detector caught **{metrics.clinical.recall * 100:.1f}%** of them."
    )
    (st.success if safe else st.error)(headline, icon="✅" if safe else "⚠️")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Clinical recall", f"{metrics.clinical.recall * 100:.1f}%", help="Primary safety metric — target ~100%")
    k2.metric("Clinical precision", f"{metrics.clinical.precision * 100:.1f}%")
    k3.metric("MDR recall", f"{metrics.mdr_recall * 100:.1f}%", help=f"over {metrics.mdr_support} candidates")
    k4.metric("Clinical auto-sent", metrics.clinical_auto_sent, help="must be 0", delta_color="inverse")

    c1, c2 = st.columns(2)
    with c1:
        st.altair_chart(ui.confusion_heatmap(metrics.clinical.confusion, "Clinical red-flag"), width="stretch")
    with c2:
        st.altair_chart(ui.confusion_heatmap(metrics.complaint.confusion, "Complaint"), width="stretch")

    st.markdown("**Dangerous misses (false negatives — must be empty)**")
    if not metrics.clinical_false_negatives:
        st.success("None — no clinical red flag was missed.", icon="✅")
    else:
        for fn in metrics.clinical_false_negatives:
            st.error(f"`{fn['id']}` ({fn['bucket']}): {fn['text']}")

    st.markdown("**Per-bucket recall**")
    rows = [
        {
            "bucket": b,
            "n": v["n"],
            "clinical recall": "—" if v["clinical_recall"] is None else f"{v['clinical_recall'] * 100:.0f}%",
            "complaint recall": "—" if v["complaint_recall"] is None else f"{v['complaint_recall'] * 100:.0f}%",
        }
        for b, v in sorted(metrics.per_bucket.items())
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
