# Milestones

## v1.0 SIP v1 Academic Deliverable (Shipped: 2026-03-02)

**Phases completed:** 11 phases, 23 plans
**Codebase:** 8,868 LOC source + 7,025 LOC tests (Python)
**Timeline:** 2026-02-25 → 2026-03-02 (6 days, 141 commits)
**Test suite:** 375 passed, 0 failures, 1 skipped

**Key accomplishments:**
1. Built RCAC (Consolidated Corruption Background Registry) from 6 sanction sources with normalized document lookups
2. Constructed M1–M4 binary labels from amendments, Comptroller bulletins, and SECOP fines
3. Engineered 34-feature pipeline (Categories A/B/C/D) with temporal leak guard and Provider History Index
4. Calibrated 11-component IRIC (Contractual Irregularity Risk Index) at national level by contract type
5. Trained 4 XGBoost classifiers with class imbalance strategy selection and 200-iteration HP search
6. Built full evaluation suite (AUC-ROC, MAP@k, NDCG@k, Brier, threshold sweep) with structured reports and charts
7. Implemented TreeSHAP explainability, Composite Risk Index (CRI), and deterministic JSON output
8. Fixed data leakage (post-amendment duration/values) and IRIC calculator key mismatches in gap-closure phases

**Tech debt accepted:**
- Phase 10 missing VERIFICATION.md (process gap)
- Trainer IRIC threshold recalibration silently fails
- Trainer encoding mappings overwrite degrades online inference
- run-pipeline CLI stub not implemented

**Archives:** `milestones/v1.0-ROADMAP.md`, `milestones/v1.0-REQUIREMENTS.md`, `milestones/v1.0-MILESTONE-AUDIT.md`

---

## v1.1 Cross-Platform OS Compatibility & Windows Support (Shipped: 2026-03-03)

**Phases completed:** 2 phases, 7 plans
**Codebase:** 8,946 LOC source + 7,038 LOC tests (Python 3.12)
**Timeline:** 2026-03-02 → 2026-03-03 (1 day, 41 commits)
**Test suite:** 375 passed, 0 failures, 1 skipped

**Key accomplishments:**
1. Hardware auto-detection (OS/CPU/RAM/GPU) with Intel/NVIDIA/AMD and container support
2. Interactive TUI config screen with live CPU/RAM/GPU monitoring and GPU benchmarking
3. GPU→CPU automatic fallback for training failures with cross-platform support
4. Windows 10 first-class support (UTF-8, safe file ops, Unicode TUI, line counting)
5. Docker CPU and NVIDIA CUDA images with multi-stage builds and non-root execution
6. GitHub Actions CI matrix with Windows Server 2022 + Ubuntu 22.04 cross-platform validation
7. Complete Windows 10 documentation and pathlib audit (confirmed zero os.path usage)

**Tech debt accepted:**
- Windows SMB path encoding edge cases not covered (rare in practice)
- ROCm on Windows not tested (Windows GPU support via CUDA only)

**Archives:** `milestones/v1.1-ROADMAP.md`, `milestones/v1.1-REQUIREMENTS.md`

---

