"""Metric logic: recall, the dangerous-miss list, and the routing safety counter."""

import pandas as pd

from vigil.evaluate import compute_metrics


def _row(**kw):
    base = dict(
        id="x", is_complaint=0, clinical_red_flag=0, potential_mdr=0,
        routing_decision="agent_draft", gold_is_complaint=0, gold_clinical_red_flag=0,
        gold_potential_mdr=0, gold_severity="none", bucket="B1", raw_text="t",
    )
    base.update(kw)
    return base


def test_perfect_clinical_recall_and_zero_autosent():
    df = pd.DataFrame([
        _row(id="1", is_complaint=1, clinical_red_flag=1, potential_mdr=1,
             routing_decision="clinical_review", gold_is_complaint=1,
             gold_clinical_red_flag=1, gold_potential_mdr=1, gold_severity="serious", bucket="B4"),
        _row(id="2", routing_decision="auto_send"),  # clean non-complaint
    ])
    m = compute_metrics(df)
    assert m.clinical.recall == 1.0
    assert m.clinical_false_negatives == []
    assert m.clinical_auto_sent == 0
    assert m.mdr_recall == 1.0


def test_false_negative_is_listed():
    df = pd.DataFrame([
        _row(id="1", is_complaint=1, clinical_red_flag=0, potential_mdr=0,
             gold_is_complaint=1, gold_clinical_red_flag=1, gold_potential_mdr=1,
             gold_severity="serious", bucket="B4", raw_text="missed loose tooth"),
    ])
    m = compute_metrics(df)
    assert m.clinical.recall == 0.0
    assert [fn["id"] for fn in m.clinical_false_negatives] == ["1"]
    assert m.mdr_recall == 0.0


def test_clinical_autosent_is_counted():
    # A gold clinical case wrongly routed to auto_send must register on the safety counter.
    df = pd.DataFrame([
        _row(id="1", routing_decision="auto_send", gold_clinical_red_flag=1,
             gold_severity="serious", bucket="B5"),
    ])
    m = compute_metrics(df)
    assert m.clinical_auto_sent == 1
