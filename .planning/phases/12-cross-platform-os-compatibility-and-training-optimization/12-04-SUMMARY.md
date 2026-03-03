---
phase: 12-cross-platform-os-compatibility-and-training-optimization
plan: 04
subsystem: data, infra
tags: [requests, curl, docker, containerization, cross-platform]

# Dependency graph
requires:
  - phase: none
    provides: standalone (no dependencies)
provides:
  - "requests fallback for data downloads on curl-less systems (Windows, minimal containers)"
  - "CPU Docker image for containerized pipeline runs"
  - "CUDA Docker image for GPU-accelerated training in containers"
affects: [deployment, ci-cd, training]

# Tech tracking
tech-stack:
  added: [requests (explicit dependency), Docker multi-stage builds]
  patterns: [curl-primary-requests-fallback download strategy, non-root container execution]

key-files:
  created:
    - Dockerfile
    - Dockerfile.cuda
    - .dockerignore
  modified:
    - src/sip_engine/data/downloader.py
    - tests/test_loaders.py

key-decisions:
  - "Kept curl as primary download method; requests is sequential fallback only"
  - "Multi-stage Docker build to minimize runtime image size"
  - "Non-root user (sip:1000) in both container images for security"
  - "CUDA image uses nvidia/cuda:12.1.0-runtime-ubuntu22.04 with deadsnakes PPA for Python 3.12"

patterns-established:
  - "Download strategy: try curl first (parallel, HTTP/2), fall back to requests (sequential)"
  - "Docker: multi-stage builds with volume mounts for data persistence"

requirements-completed: [PLAT-07, PLAT-08]

# Metrics
duration: 5min
completed: 2026-03-03
---

# Phase 12 Plan 04: Requests Fallback & Docker Support Summary

**Curl-primary/requests-fallback download strategy with multi-stage Docker images for CPU and CUDA containerized execution**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-03T19:54:54Z
- **Completed:** 2026-03-03T19:59:43Z
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments
- Data downloader now works on systems without curl (Windows, minimal containers) via Python requests fallback
- CPU Docker image (multi-stage, Python 3.12-slim) supports all sip-engine CLI commands
- CUDA Docker image (nvidia/cuda:12.1.0) enables GPU training in containers
- All 28 loader tests pass including 3 new downloader tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Add requests fallback to downloader.py** - `7c85621` (feat)
2. **Task 2: Create Dockerfiles for CPU and CUDA runs** - `9899921` (feat)

## Files Created/Modified
- `src/sip_engine/data/downloader.py` - Added _curl_available(), _download_with_requests(), and fallback branch in download_datasets()
- `tests/test_loaders.py` - Added TestDownloaderCurlFallback class with 3 tests
- `Dockerfile` - Multi-stage CPU-only image (python:3.12-slim, non-root user)
- `Dockerfile.cuda` - CUDA-enabled image (nvidia/cuda:12.1.0, Python 3.12 via deadsnakes)
- `.dockerignore` - Excludes data, artifacts, dev files from Docker context

## Decisions Made
- **Curl remains primary:** The existing parallel curl implementation is battle-tested with progress bars, stall detection, and HTTP/2. Requests fallback is sequential and simpler — only used when curl is unavailable.
- **Sequential requests fallback:** Rather than building a complex threaded requests download system, implemented a simple sequential fallback. Functional correctness over performance parity — systems without curl are edge cases.
- **Multi-stage Dockerfile:** Builder stage has build-essential for compiling C extensions; runtime stage is slim with only curl added. Reduces image size significantly.
- **Non-root container user:** Both images create `sip:1000` user for security best practices.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
- pytest needed to be installed in venv (quick `uv pip install pytest` fix)

## Next Phase Readiness
- Docker images ready for CI/CD integration
- Requests fallback enables Windows/container deployment without curl dependency
- All existing tests continue to pass (28/28)

---
*Phase: 12-cross-platform-os-compatibility-and-training-optimization*
*Completed: 2026-03-03*
