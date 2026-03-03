# Roadmap: SIP — Intelligent Prediction System for Corruption in Public Procurement

## Milestones

- ✅ **v1.0 Academic Deliverable** — Phases 1–11 (shipped 2026-03-02)

## Phases

<details>
<summary>✅ v1.0 Academic Deliverable (Phases 1–11) — SHIPPED 2026-03-02</summary>

- [x] Phase 1: Project Foundation (2/2 plans) — completed 2026-03-01
- [x] Phase 2: Data Loaders (2/2 plans) — completed 2026-03-01
- [x] Phase 3: RCAC Builder (2/2 plans) — completed 2026-03-01
- [x] Phase 4: Label Construction (2/2 plans) — completed 2026-03-01
- [x] Phase 5: Feature Engineering (3/3 plans) — completed 2026-03-01
- [x] Phase 6: IRIC (3/3 plans) — completed 2026-03-02
- [x] Phase 7: Model Training (2/2 plans) — completed 2026-03-02
- [x] Phase 8: Evaluation (2/2 plans) — completed 2026-03-02
- [x] Phase 9: Explainability, CRI, and Testing (2/2 plans) — completed 2026-03-02
- [x] Phase 10: Data Leakage Fix (2/2 plans) — completed 2026-03-02 *(Gap Closure)*
- [x] Phase 11: Bug Fixes and Test Cleanup (1/1 plan) — completed 2026-03-02 *(Gap Closure)*

**Full details:** `milestones/v1.0-ROADMAP.md`

</details>

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. Project Foundation | v1.0 | 2/2 | Complete | 2026-03-01 |
| 2. Data Loaders | v1.0 | 2/2 | Complete | 2026-03-01 |
| 3. RCAC Builder | v1.0 | 2/2 | Complete | 2026-03-01 |
| 4. Label Construction | v1.0 | 2/2 | Complete | 2026-03-01 |
| 5. Feature Engineering | v1.0 | 3/3 | Complete | 2026-03-01 |
| 6. IRIC | v1.0 | 3/3 | Complete | 2026-03-02 |
| 7. Model Training | v1.0 | 2/2 | Complete | 2026-03-02 |
| 8. Evaluation | v1.0 | 2/2 | Complete | 2026-03-02 |
| 9. Explainability, CRI, Testing | v1.0 | 2/2 | Complete | 2026-03-02 |
| 10. Data Leakage Fix | v1.0 | 2/2 | Complete | 2026-03-02 |
| 11. Bug Fixes and Test Cleanup | v1.0 | 1/1 | Complete | 2026-03-02 |
| 12. Cross-platform OS Compatibility & Training Optimization | — | 4 | Planned | — |

### Phase 12: Cross-platform OS Compatibility and Training Optimization

**Goal:** Full cross-platform OS compatibility (macOS/Linux/Windows/Docker) with auto-hardware detection, interactive TUI config, GPU acceleration with fallback, and rich training progress
**Depends on:** Phase 11
**Requirements:** [PLAT-01, PLAT-02, PLAT-03, PLAT-04, PLAT-05, PLAT-06, PLAT-07, PLAT-08]
**Plans:** 4 plans

Plans:
- [ ] 12-01-PLAN.md — Hardware detection foundation (OS, CPU, RAM, GPU detection + benchmark)
- [ ] 12-02-PLAN.md — Interactive TUI components (config screen + training progress)
- [ ] 12-03-PLAN.md — Training pipeline integration (wire hardware + TUI + GPU fallback + CLI flags)
- [ ] 12-04-PLAN.md — Cross-platform curl fallback + Docker support
