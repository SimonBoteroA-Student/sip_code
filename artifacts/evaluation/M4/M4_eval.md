# Evaluation Report — Model M4

| Property | Value |
|----------|-------|
| Evaluation date | 2026-03-02T18:41:28.788372+00:00 |
| Test set size | 94,802 |
| Positives | 272 (0.29%) |
| Negatives | 94,530 (99.71%) |

---

## 1. Discrimination — ROC Curve

| Metric | Value |
|--------|-------|
| **AUC-ROC** | **0.8641** |

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
| 0.05 | 0.0031 | 0.9963 | 0.0062 | 7,704 | 86,826 | 1 | 271 |
| 0.10 | 0.0073 | 0.8162 | 0.0145 | 64,454 | 30,076 | 50 | 222 |
| 0.15 | 0.0142 | 0.7206 | 0.0278 | 80,908 | 13,622 | 76 | 196 |
| 0.20 | 0.0194 | 0.7022 | 0.0377 | 84,870 | 9,660 | 81 | 191 |
| 0.25 | 0.0240 | 0.6544 | 0.0463 | 87,287 | 7,243 | 94 | 178 |
| 0.30 | 0.0308 | 0.6287 | 0.0587 | 89,148 | 5,382 | 101 | 171 |
| 0.35 | 0.0389 | 0.5993 | 0.0730 | 90,502 | 4,028 | 109 | 163 |
| 0.40 | 0.0497 | 0.5772 | 0.0916 | 91,530 | 3,000 | 115 | 157 |
| 0.45 | 0.0618 | 0.5368 | 0.1109 | 92,314 | 2,216 | 126 | 146 |
| 0.50 | 0.0809 | 0.5294 | 0.1404 | 92,894 | 1,636 | 128 | 144 |
| 0.55 | 0.0981 | 0.4816 | 0.1629 | 93,325 | 1,205 | 141 | 131 |
| 0.60 | 0.1188 | 0.4485 | 0.1878 | 93,625 | 905 | 150 | 122 |
| 0.65 | 0.1541 | 0.4191 | 0.2253 | 93,904 | 626 | 158 | 114 |
| 0.70 | 0.1853 | 0.3787 | 0.2488 | 94,077 | 453 | 169 | 103 |
| 0.75 | 0.2468 | 0.3529 | 0.2905 | 94,237 | 293 | 176 | 96 |
| 0.80 | 0.3188 | 0.3235 | 0.3212 | 94,342 | 188 | 184 | 88 |
| 0.85 **←** | 0.4148 | 0.2684 | 0.3259 | 94,427 | 103 | 199 | 73 |
| 0.90 | 0.5464 | 0.1949 | 0.2873 | 94,486 | 44 | 219 | 53 |
| 0.95 | 0.8333 | 0.0551 | 0.1034 | 94,527 | 3 | 257 | 15 |

</details>

---

## 4. Optimal Threshold & Confusion Matrix

**Recommended operating point (F1-maximizing):** threshold = **0.85**

| Metric | Value |
|--------|------:|
| Threshold | 0.85 |
| Precision | 0.4148 |
| Recall | 0.2684 |
| F1 | 0.3259 |
| TN | 94,427 |
| FP | 103 |
| FN | 199 |
| TP | 73 |

![Confusion Matrix](images/confusion_matrix.png)

---

## 5. Ranking Metrics

| Metric | Value |
|--------|------:|
| MAP@100 | 0.7590 |
| MAP@500 | 0.5978 |
| MAP@1000 | 0.5217 |
| NDCG@100 | 0.6193 |
| NDCG@500 | 0.4299 |
| NDCG@1000 | 0.4805 |

![Ranking Metrics](images/ranking_metrics.png)

---

## 6. Calibration

| Metric | Value |
|--------|------:|
| Brier Score | 0.0243 |
| Brier Baseline (random) | 0.0029 |

> Lower Brier Score = better calibration. Baseline = positive_rate × (1 − positive_rate).

![Calibration](images/calibration_summary.png)

---

## 7. Training Context

**Imbalance strategy:** upsampling_25pct

**Best hyperparameters:**

| Parameter | Value |
|-----------|------:|
| colsample_bytree | 0.6762844281670846 |
| gamma | 0.5 |
| learning_rate | 0.010239273411172712 |
| max_depth | 5 |
| min_child_weight | 9 |
| n_estimators | 367 |
| reg_alpha | 0 |
| reg_lambda | 0 |
| subsample | 0.5599326836668415 |

---

*Report generated automatically by SIP Engine evaluation module.*  
*See companion JSON and CSV files for machine-readable data.*
