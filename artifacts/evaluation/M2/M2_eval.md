# Evaluation Report — Model M2

| Property | Value |
|----------|-------|
| Evaluation date | 2026-03-02T18:41:26.271500+00:00 |
| Test set size | 95,098 |
| Positives | 6 (0.01%) |
| Negatives | 95,092 (99.99%) |

---

## 1. Discrimination — ROC Curve

| Metric | Value |
|--------|-------|
| **AUC-ROC** | **0.9961** |

![ROC Curve](images/roc_curve.png)

---

## 2. Score Distribution

![Score Distribution](images/score_distribution.png)

---

## 3. Precision / Recall / F1 vs. Threshold

![Precision-Recall-F1](images/precision_recall_f1.png)

<details>
<summary>Threshold Analysis Table (click to expand)</summary>

| Threshold | Precision | Recall | F1 | TN | FP | FN | TP |
|:---------:|:---------:|:------:|:--:|---:|---:|---:|---:|
| 0.05 | 0.0001 | 1.0000 | 0.0001 | 0 | 95,092 | 0 | 6 |
| 0.10 | 0.0001 | 1.0000 | 0.0001 | 0 | 95,092 | 0 | 6 |
| 0.15 | 0.0001 | 1.0000 | 0.0001 | 0 | 95,092 | 0 | 6 |
| 0.20 | 0.0012 | 1.0000 | 0.0025 | 90,282 | 4,810 | 0 | 6 |
| 0.25 | 0.0048 | 1.0000 | 0.0096 | 93,860 | 1,232 | 0 | 6 |
| 0.30 | 0.0078 | 0.8333 | 0.0154 | 94,454 | 638 | 1 | 5 |
| 0.35 | 0.0081 | 0.5000 | 0.0160 | 94,726 | 366 | 3 | 3 |
| 0.40 | 0.0100 | 0.5000 | 0.0195 | 94,794 | 298 | 3 | 3 |
| 0.45 | 0.0106 | 0.5000 | 0.0207 | 94,811 | 281 | 3 | 3 |
| 0.50 | 0.0115 | 0.5000 | 0.0224 | 94,833 | 259 | 3 | 3 |
| 0.55 | 0.0132 | 0.5000 | 0.0258 | 94,868 | 224 | 3 | 3 |
| 0.60 | 0.0112 | 0.3333 | 0.0216 | 94,915 | 177 | 4 | 2 |
| 0.65 | 0.0147 | 0.3333 | 0.0282 | 94,958 | 134 | 4 | 2 |
| 0.70 | 0.0110 | 0.1667 | 0.0206 | 95,002 | 90 | 5 | 1 |
| 0.75 | 0.0227 | 0.1667 | 0.0400 | 95,049 | 43 | 5 | 1 |
| 0.80 **←** | 0.0909 | 0.1667 | 0.1176 | 95,082 | 10 | 5 | 1 |
| 0.85 | 0.0000 | 0.0000 | 0.0000 | 95,092 | 0 | 6 | 0 |
| 0.90 | 0.0000 | 0.0000 | 0.0000 | 95,092 | 0 | 6 | 0 |
| 0.95 | 0.0000 | 0.0000 | 0.0000 | 95,092 | 0 | 6 | 0 |

</details>

---

## 4. Optimal Threshold & Confusion Matrix

**Recommended operating point (F1-maximizing):** threshold = **0.8**

| Metric | Value |
|--------|------:|
| Threshold | 0.8 |
| Precision | 0.0909 |
| Recall | 0.1667 |
| F1 | 0.1176 |
| TN | 95,082 |
| FP | 10 |
| FN | 5 |
| TP | 1 |

![Confusion Matrix](images/confusion_matrix.png)

---

## 5. Ranking Metrics

| Metric | Value |
|--------|------:|
| MAP@100 | 0.1000 |
| MAP@500 | 0.0302 |
| MAP@1000 | 0.0302 |
| NDCG@100 | 0.0875 |
| NDCG@500 | 0.2390 |
| NDCG@1000 | 0.2390 |

![Ranking Metrics](images/ranking_metrics.png)

---

## 6. Calibration

| Metric | Value |
|--------|------:|
| Brier Score | 0.0361 |
| Brier Baseline (random) | 0.0001 |

> Lower Brier Score = better calibration. Baseline = positive_rate × (1 − positive_rate).

![Calibration](images/calibration_summary.png)

---

## 7. Training Context

**Imbalance strategy:** scale_pos_weight

**Best hyperparameters:**

| Parameter | Value |
|-----------|------:|
| colsample_bytree | 0.7542853455823514 |
| gamma | 0.1 |
| learning_rate | 0.016062363601797407 |
| max_depth | 7 |
| min_child_weight | 4 |
| n_estimators | 62 |
| reg_alpha | 1.0 |
| reg_lambda | 5 |
| subsample | 0.8473924665198522 |

---

*Report generated automatically by SIP Engine evaluation module.*  
*See companion JSON and CSV files for machine-readable data.*
