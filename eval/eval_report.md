# Vigil — Eval Report

_Model: `claude-sonnet-4-6` · prompt `v2` · 97 messages · temperature 0.0_

## Headline

✅ **Across 97 messages, 0 clinical red flags were auto-answered, and the clinical red-flag detector caught 100.0% of them (reportable-injury recall 93.8% over 32 candidates).**

## Clinical red-flag detector (PRIMARY — recall is the safety metric)

- **Recall: 100.0%** (target ~100%)
- Precision: 98.1%  ·  F1: 99.1%  ·  positives in set: 53

| | predicted 0 | predicted 1 |
|---|---:|---:|
| **actual 0** | 43 | 1 |
| **actual 1** | 0 | 53 |


### Dangerous misses (false negatives — must be empty)

None. ✅ No clinical red flag was missed.

## Complaint detector (FDA 21 CFR 820.3(b))

- Precision: 100.0%  ·  Recall: 93.1%  ·  F1: 96.4%  ·  positives: 72

| | predicted 0 | predicted 1 |
|---|---:|---:|
| **actual 0** | 25 | 0 |
| **actual 1** | 5 | 67 |


## MDR-potential (reportable-injury candidates)

- Recall over the 32 serious/MDR-candidate cases: **93.8%**

## Routing safety check

- Clinical cases that were auto-sent: **0** (must be 0) ✅

## Per-bucket breakdown

| bucket | n | clinical recall | complaint recall |
|---|---:|---:|---:|
| B1_non_complaint | 20 | — | — |
| B2_complaint_non_clinical | 19 | — | 89.5% |
| B3_clinical_non_serious | 19 | 100.0% | 89.5% |
| B4_clinical_serious | 19 | 100.0% | 100.0% |
| B5_adversarial | 20 | 100.0% | 93.3% |
