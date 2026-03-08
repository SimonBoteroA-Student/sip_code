# Roadmap: SIP — Intelligent Prediction System for Corruption in Public Procurement

## Milestones

- ✅ **v1.0 Academic Deliverable** — Phases 1–11 (shipped 2026-03-02)
- ✅ **v1.1 Cross-Platform OS Compatibility & Windows Support** — Phases 12–13 (shipped 2026-03-03)
- 🔄 **v1.2 CLI & TUI Polish** — Phase 14 (1/2 plans complete)

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
| 12. Cross-platform OS Compatibility & Training Optimization | v1.1 | 4/4 | Complete | 2026-03-03 |
| 13. Windows 10 Compatibility | v1.1 | 3/3 | Complete | 2026-03-03 |
| 14. CLI & TUI Fixes — Command Pipeline Refactor | 2/2 | Complete    | 2026-03-06 | — |
| 15. Evaluation & Training Enhancements | — | 1/3 | In Progress | — |

<details>
<summary>✅ v1.1 Cross-Platform OS Compatibility & Windows Support (Phases 12–13) — SHIPPED 2026-03-03</summary>

- [x] Phase 12: Cross-platform OS Compatibility and Training Optimization (4/4 plans) — completed 2026-03-03
  - [x] 12-01: Hardware detection foundation (OS, CPU, RAM, GPU detection + benchmark)
  - [x] 12-02: Interactive TUI components (config screen + training progress)
  - [x] 12-03: Training pipeline integration (wire hardware + TUI + GPU fallback + CLI flags)
  - [x] 12-04: Cross-platform curl fallback + Docker support
- [x] Phase 13: Windows 10 Compatibility (3/3 plans) — completed 2026-03-03
  - [x] 13-01: Platform compat layer + consumer integration (UTF-8, safe_rename, count_lines, Unicode degradation)
  - [x] 13-02: Hardware detection + benchmark Windows fixes (nvidia-smi path, ROCm guard, ThreadPoolExecutor timeout)
  - [x] 13-03: GitHub Actions CI with Windows matrix + pathlib audit + README docs

**Full details:** `milestones/v1.1-ROADMAP.md`

</details>

### Phase 14: CLI & TUI Fixes — Command Pipeline Refactor

**Goal:** Fix chart edge clipping, restore hardware config display and title in TUI, refactor CLI commands so `run-pipeline` acts as a master orchestrator calling individual subcommands, and centralize hardware config prompting at pipeline start.
**Depends on:** Phase 13
**Plans:** 2/2 plans complete

Plans:
- [ ] 14-01-PLAN.md — Fix TUI rendering bugs (Layout instead of Group for screen mode)
- [x] 14-02-PLAN.md — Pipeline coordinator + CLI refactor (PipelineConfig, run_*() functions, --start-from)

### Phase 15: Evaluation and Training Module Enhancements — AUC-PR, Model Selector, Brier Skill Score, and Named Model Artifacts

**Goal:** Add AUC-PR and Brier Skill Score metrics to evaluation, implement multi-model --model selector with TUI picker, and introduce named/versioned model artifacts with flat archival and --artifact evaluation flag.
**Depends on:** Phase 14
**Plans:** 3 plans

Plans:
- [x] 15-01-PLAN.md — AUC-PR + Brier Skill Score metrics (evaluator + visualizer + reports)
- [x] 15-02-PLAN.md — Named model artifacts (trainer flat archiving + --artifact eval flag)
- [ ] 15-03-PLAN.md — Model selector TUI + --model nargs='+' (CLI + pipeline + picker)
