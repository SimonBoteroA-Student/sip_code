# Phase 13: Windows 10 Compatibility - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the SIP pipeline fully first-class on Windows 10: fix all runtime issues, ensure installation is clean, add CI regression testing on Windows, and harden platform-specific behavior (paths, encoding, GPU detection, multiprocessing, TUI). No new ML models, features, or cloud infrastructure — cloud deployment is a future phase; this phase must not complicate it.

</domain>

<decisions>
## Implementation Decisions

### Target Environment
- Primary terminal: Windows Terminal + PowerShell 7 (best Unicode/color support)
- Installation: via `uv` (already used in project) — document `uv run sip-engine` invocation in README
- No wrapper scripts (.bat / .ps1) — just README documentation
- CLI entry point (`[project.scripts]` in pyproject.toml) installs as `sip-engine.exe` automatically via uv

### GitHub Actions CI
- Add `windows-latest` runner to existing GitHub Actions workflow
- Run full test suite (all 413 tests) on Windows — no subset
- Windows CI must stay green as part of phase completion criteria

### Path Handling
- Full pathlib audit of entire codebase — replace all `os.path.*` and string-concatenated paths with `pathlib.Path`
- No hardcoded path separators anywhere
- All file operations use `Path` objects throughout

### Unicode / TUI
- Graceful degradation: detect when block characters (█/░) are not supported by the terminal
- Fall back to ASCII art slider representation (e.g., `[########.......]`) when Unicode block chars unavailable
- Rich library handles most of this; any gaps patched manually

### Console Encoding (UTF-8)
- On Windows, if `sys.stdout.encoding` is not UTF-8 (e.g., cp1252), programmatically set `PYTHONIOENCODING=utf-8` at startup and reconfigure stdout
- Ensures SHAP symbols, progress characters, and Unicode output render correctly without user intervention

### GPU Detection (CUDA on Windows)
- Try `nvidia-smi` first (works when NVIDIA drivers are installed and in PATH)
- Fall back to `C:\Windows\System32\nvidia-smi.exe` full path if not in PATH
- pynvml remains the primary method for GPU name/VRAM — more portable; nvidia-smi path fallback applies as secondary
- ROCm on Windows: not supported (out of scope for this phase)

### Multiprocessing (Joblib / CPU Parallelism)
- Research first: determine whether joblib's `loky` backend with `spawn` context is fully functional on Windows for `RandomizedSearchCV(n_jobs=N)` and any other parallel operations
- If a spawn-safe approach exists (e.g., `loky` backend with proper `if __name__ == '__main__'` guards in `__main__.py`), implement it to preserve full CPU parallelism on Windows
- If parallel execution is not reliable on Windows: fall back to sequential (`n_jobs=1`) automatically but warn the user clearly
- Goal: make the most of available CPU cores on Windows — sequential is the last resort, not the default
- XGBoost internal threading (`nthread`) is unaffected — this is about sklearn's HP search parallelism only

### Temp File Handling (Downloader)
- OS-specific behavior: on Unix, keep current `.csv.part` rename approach (atomic, safe)
- On Windows: use a different strategy to avoid file locking issues (e.g., `shutil.move` with retry, or write to a separate temp path and copy rather than rename)
- Wrap any rename/delete in `PermissionError` handlers with retry logic on Windows

### Cloud Readiness Constraint
- Nothing in this phase should complicate future cloud deployment
- Docker support from Phase 12 (Dockerfile, Dockerfile.cuda) must remain fully functional
- Any multiprocessing or path changes must work correctly in Linux containers

### Claude's Discretion
- Exact ASCII fallback representation for sliders
- Specific retry logic implementation for Windows file rename
- Whether to use `sys.stdout.reconfigure(encoding='utf-8')` or `PYTHONUTF8=1` env approach
- Exact structure of GitHub Actions Windows job (matrix vs separate job)
- How to detect Unicode terminal support (checking TERM, WT_SESSION, or attempting test write)

</decisions>

<specifics>
## Specific Ideas

- User specifically wants maximum CPU parallelism on Windows — research spawn-safe joblib approaches thoroughly before defaulting to sequential
- User has an NVIDIA GPU for training on Windows — CUDA detection and full GPU training must work
- Cloud deployment is a future phase — this phase must not break Docker compatibility or add Windows-only code paths that would fail in Linux containers
- Use `uv run sip-engine` as the documented Windows invocation — consistent with macOS/Linux workflow

</specifics>

<deferred>
## Deferred Ideas

- Cloud deployment infrastructure (Docker CI/CD, cloud runner, environment config) — future phase
- ROCm on Windows — AMD GPU support not in scope for Windows 10 phase
- .bat / .ps1 wrapper scripts — not needed given uv workflow
- Windows Defender / antivirus considerations — out of scope

</deferred>

---

*Phase: 13-windows-10-compatibility*
*Context gathered: 2026-03-03*
