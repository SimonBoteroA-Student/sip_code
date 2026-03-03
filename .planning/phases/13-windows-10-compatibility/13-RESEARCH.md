# Phase 13: Windows 10 Compatibility - Research

**Researched:** 2026-03-03
**Domain:** Cross-platform Python compatibility (Windows 10 + PowerShell 7 / Windows Terminal)
**Confidence:** HIGH

## Summary

The SIP engine codebase is already well-structured for cross-platform support: it uses `pathlib.Path` throughout (zero `os.path.*` calls), has cross-platform keyboard input handlers, and applies `platform.system()` checks for benchmark timeouts. However, several concrete issues must be fixed for Windows 10 first-class support: (1) `wc -l` subprocess call for line counting fails on Windows, (2) `Path.rename()` for temp file finalization is not atomic on Windows and fails when target exists, (3) `nvidia-smi` search path needs Windows fallback to `C:\Windows\System32\nvidia-smi.exe`, (4) ROCm detection checks a Unix-only path (`/opt/rocm`), (5) ANSI escape codes used for download progress (`\033[A\033[2K`) need Windows Terminal / VT processing, (6) `open()` calls in `comparison.py` omit `encoding='utf-8'`, (7) console encoding may default to cp1252 on older Windows setups, (8) `signal.SIGINT` in the downloader may behave differently on Windows, and (9) the benchmark module's Windows timeout via `threading.Timer` doesn't actually interrupt the training — it just sets a timer that does nothing (`lambda: None`).

The HP search is already sequential (manual CV loops, not `RandomizedSearchCV`), so joblib/loky multiprocessing for HP search is a non-issue. Joblib is only used for `joblib.dump/load` (serialization), not parallel execution. XGBoost's internal `nthread` parallelism works fine on Windows.

**Primary recommendation:** Audit the 9 concrete issues above, add a `_platform_init()` function for UTF-8 console encoding at startup, create a `_safe_rename()` utility with retry logic for Windows temp file handling, add a pure-Python line counter fallback for `wc -l`, extend CUDA detection with Windows nvidia-smi path fallback, add Unicode/ASCII graceful degradation for TUI sliders, and establish a `windows-latest` GitHub Actions CI job running all 413 tests.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Primary terminal: Windows Terminal + PowerShell 7 (best Unicode/color support)
- Installation: via `uv` (already used in project) — document `uv run sip-engine` invocation in README
- No wrapper scripts (.bat / .ps1) — just README documentation
- CLI entry point (`[project.scripts]` in pyproject.toml) installs as `sip-engine.exe` automatically via uv
- Add `windows-latest` runner to existing GitHub Actions workflow
- Run full test suite (all 413 tests) on Windows — no subset
- Windows CI must stay green as part of phase completion criteria
- Full pathlib audit of entire codebase — replace all `os.path.*` and string-concatenated paths with `pathlib.Path`
- No hardcoded path separators anywhere
- All file operations use `Path` objects throughout
- Graceful degradation: detect when block characters (█/░) are not supported by the terminal
- Fall back to ASCII art slider representation (e.g., `[########.......]`) when Unicode block chars unavailable
- Rich library handles most of this; any gaps patched manually
- On Windows, if `sys.stdout.encoding` is not UTF-8 (e.g., cp1252), programmatically set `PYTHONIOENCODING=utf-8` at startup and reconfigure stdout
- Try `nvidia-smi` first (works when NVIDIA drivers are installed and in PATH)
- Fall back to `C:\Windows\System32\nvidia-smi.exe` full path if not in PATH
- pynvml remains the primary method for GPU name/VRAM — more portable; nvidia-smi path fallback applies as secondary
- ROCm on Windows: not supported (out of scope)
- Research first: determine whether joblib's `loky` backend with `spawn` context is fully functional on Windows for `RandomizedSearchCV(n_jobs=N)` and any other parallel operations
- If a spawn-safe approach exists, implement it to preserve full CPU parallelism on Windows
- If parallel execution is not reliable on Windows: fall back to sequential (`n_jobs=1`) automatically but warn the user clearly
- OS-specific behavior: on Unix, keep current `.csv.part` rename approach (atomic, safe)
- On Windows: use a different strategy to avoid file locking issues
- Wrap any rename/delete in `PermissionError` handlers with retry logic on Windows
- Nothing in this phase should complicate future cloud deployment
- Docker support from Phase 12 (Dockerfile, Dockerfile.cuda) must remain fully functional
- Any multiprocessing or path changes must work correctly in Linux containers

### Claude's Discretion
- Exact ASCII fallback representation for sliders
- Specific retry logic implementation for Windows file rename
- Whether to use `sys.stdout.reconfigure(encoding='utf-8')` or `PYTHONUTF8=1` env approach
- Exact structure of GitHub Actions Windows job (matrix vs separate job)
- How to detect Unicode terminal support (checking TERM, WT_SESSION, or attempting test write)

### Deferred Ideas (OUT OF SCOPE)
- Cloud deployment infrastructure (Docker CI/CD, cloud runner, environment config) — future phase
- ROCm on Windows — AMD GPU support not in scope for Windows 10 phase
- .bat / .ps1 wrapper scripts — not needed given uv workflow
- Windows Defender / antivirus considerations — out of scope
</user_constraints>

## Standard Stack

### Core (Already in Project)
| Library | Version | Purpose | Windows Status |
|---------|---------|---------|----------------|
| pathlib | stdlib | Path handling | ✅ Fully cross-platform |
| XGBoost | >=2.0 | ML training | ✅ Windows wheels available, CUDA works |
| Rich | >=13.0 | TUI/progress | ✅ Windows Terminal VT support |
| psutil | >=5.9 | System info | ✅ Windows API support built-in |
| joblib | >=1.4 | Serialization | ✅ dump/load works on Windows |
| requests | >=2.31 | HTTP downloads | ✅ Cross-platform |
| matplotlib | >=3.8 | Chart generation | ✅ Agg backend is headless |

### Supporting (No New Dependencies)
| Library | Purpose | Windows Notes |
|---------|---------|---------------|
| msvcrt | Keyboard input | ✅ Already used in config_screen.py |
| subprocess | nvidia-smi, curl | ⚠️ Need `creationflags` for clean process handling |
| shutil | File moves | ⚠️ Windows file locking may cause failures |
| signal | SIGINT handler | ⚠️ Limited on Windows (no SIGALRM) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `sys.stdout.reconfigure(encoding='utf-8')` | `PYTHONUTF8=1` env var | reconfigure is simpler and more targeted; PYTHONUTF8 is global but may not take effect if set after interpreter startup |
| matrix CI strategy | separate Windows job | matrix is cleaner but couples Windows/macOS/Linux failures; **recommend matrix** for consistency |
| Pure-Python `_count_lines()` | `wc -l` only | Must have Python fallback since `wc` doesn't exist on Windows |

## Architecture Patterns

### Recommended Approach: Platform Compatibility Layer
Rather than scattering `if sys.platform == "win32"` checks throughout the codebase, create a thin compatibility module:

```
src/sip_engine/
├── compat.py              # NEW: platform utilities module
│   ├── safe_rename()      # Path.rename with retry on Windows
│   ├── count_lines()      # wc -l with Python fallback
│   ├── ensure_utf8_console()  # UTF-8 stdout on Windows
│   └── supports_unicode_blocks()  # detect Unicode support
├── hardware/
│   └── detector.py        # MODIFY: nvidia-smi Windows path, ROCm skip on Windows
├── ui/
│   └── config_screen.py   # MODIFY: ASCII fallback for slider bar chars
├── data/
│   ├── downloader.py      # MODIFY: safe_rename, signal compat
│   └── loaders.py         # MODIFY: use count_lines() from compat
└── __main__.py            # MODIFY: call ensure_utf8_console() at startup
```

### Pattern 1: Safe File Rename with Retry
**What:** `Path.rename()` on Windows fails if the target exists (unlike Unix where it's atomic overwrite). Windows also has file locking from antivirus/indexers.
**When to use:** Every temp file → final file rename in `downloader.py`.
**Example:**
```python
import sys
import time
from pathlib import Path

def safe_rename(src: Path, dest: Path, retries: int = 3, delay: float = 0.5) -> None:
    """Rename src to dest, with retry logic for Windows file locking."""
    for attempt in range(retries):
        try:
            if sys.platform == "win32" and dest.exists():
                dest.unlink()
            src.rename(dest)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                raise
```

### Pattern 2: UTF-8 Console Initialization
**What:** Windows default encoding can be cp1252; SHAP symbols and Spanish characters need UTF-8.
**When to use:** At application startup, before any output.
**Example:**
```python
import sys

def ensure_utf8_console() -> None:
    """Ensure stdout/stderr use UTF-8 on Windows."""
    if sys.platform != "win32":
        return
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except AttributeError:
            pass  # Python < 3.7 safety (won't happen with 3.12)
```

### Pattern 3: Unicode Block Char Detection
**What:** Detect whether terminal supports Unicode block characters (█/░) for slider rendering.
**When to use:** In config_screen.py before rendering sliders.
**Example:**
```python
import os
import sys

def supports_unicode_blocks() -> bool:
    """Detect if the terminal can render Unicode block characters."""
    # Windows Terminal sets WT_SESSION env var
    if os.environ.get("WT_SESSION"):
        return True
    # Check encoding
    enc = getattr(sys.stdout, "encoding", "") or ""
    if "utf" in enc.lower():
        return True
    # Fallback: try writing and checking
    return False
```

### Anti-Patterns to Avoid
- **Scattering `if sys.platform == "win32"` everywhere:** Centralize in `compat.py` — makes testing and maintenance manageable.
- **Using `os.path` or string-based path concatenation:** Already avoided — project uses pathlib throughout. Don't regress.
- **Catching bare `Exception` for file operations:** Catch `PermissionError` and `OSError` specifically — more debuggable.
- **Breaking Docker/Linux behavior to fix Windows:** Every change must work on both — always test with the full suite.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unicode terminal detection | Custom escape sequence probing | `WT_SESSION` env check + encoding check | Reliable on Windows Terminal + PowerShell 7 which is our target |
| Keyboard input on Windows | Custom Win32 API calls | `msvcrt.getwch()` | Already implemented in config_screen.py |
| ANSI escape on Windows | VT sequence enabler | Rich library | Rich already handles Windows ANSI via `colorama` or VT processing |
| Process-safe temp files | Custom locking | `safe_rename()` with retry | Simple retry handles 99% of Windows file locking issues |
| GPU detection | WMI queries | pynvml + nvidia-smi fallback | pynvml is already used; WMI adds unnecessary complexity |

**Key insight:** Rich handles most Windows TUI concerns automatically. The manual gaps are: (a) the custom `_FILLED`/`_EMPTY` chars in slider rendering and (b) raw `\033[` escape codes in the downloader progress display.

## Common Pitfalls

### Pitfall 1: Path.rename() Cross-Device / Target-Exists on Windows
**What goes wrong:** `Path.rename()` on Windows raises `FileExistsError` if the target already exists. On Unix, rename atomically overwrites.
**Why it happens:** Windows NTFS doesn't support atomic rename-over-existing.
**How to avoid:** Use `safe_rename()` pattern: delete target first, then rename, with PermissionError retry.
**Warning signs:** `FileExistsError` or `PermissionError` during download finalization on Windows.
**Files affected:** `downloader.py` lines 220, 531.

### Pitfall 2: `wc -l` Doesn't Exist on Windows
**What goes wrong:** `_count_lines()` in `loaders.py` calls `wc -l` via subprocess — always returns 0 on Windows (caught as OSError).
**Why it happens:** `wc` is a Unix utility, not available on Windows.
**How to avoid:** Add a pure-Python line counter fallback. The current code already handles the failure gracefully (returns 0, tqdm shows spinner), but a proper fallback would improve UX by showing actual progress bars.
**Warning signs:** Progress bars show spinner instead of percentage on Windows.
**Files affected:** `loaders.py` line 79.

### Pitfall 3: Windows Console Default Encoding (cp1252)
**What goes wrong:** Spanish characters (CÉDULA DE CIUDADANÍA), SHAP symbols, and Unicode progress chars cause `UnicodeEncodeError` on print.
**Why it happens:** Windows PowerShell 5 / cmd.exe defaults to cp1252 or OEM codepage. Even PowerShell 7 in Windows Terminal may need explicit UTF-8 mode.
**How to avoid:** Call `sys.stdout.reconfigure(encoding='utf-8')` at application startup. Also set `PYTHONUTF8=1` as documented fallback.
**Warning signs:** `UnicodeEncodeError` when printing SHAP waterfall results or Spanish entity names.
**Files affected:** `__main__.py` (add at top of `main()`).

### Pitfall 4: signal.SIGINT Behavior Differences on Windows
**What goes wrong:** `signal.signal(signal.SIGINT, handler)` works on Windows but with different semantics — the handler may not fire reliably for subprocesses managed by `subprocess.Popen`.
**Why it happens:** Windows doesn't have Unix-style signal delivery. Ctrl+C generates `CTRL_C_EVENT`.
**How to avoid:** The existing code in `downloader.py` uses `signal.signal(signal.SIGINT, ...)` which does work on Windows for the main process. The curl subprocesses should be created with `subprocess.CREATE_NEW_PROCESS_GROUP` to allow independent termination. Or rely on the requests fallback (which is already the default on Windows since curl may not be available).
**Warning signs:** Ctrl+C hangs or doesn't clean up properly on Windows.
**Files affected:** `downloader.py` lines 491-552.

### Pitfall 5: ANSI Escape Codes in Downloader Progress
**What goes wrong:** `_clear_lines()` uses raw `\033[A\033[2K` escape codes. These work in Windows Terminal but NOT in legacy cmd.exe or older PowerShell.
**Why it happens:** Windows Terminal enables VT processing by default, but the code path for curl-based downloads (which won't be used on Windows anyway since curl may not be there) still has these raw escapes.
**How to avoid:** The requests fallback (used when curl is unavailable) doesn't use `_clear_lines()`. Since curl is unlikely on Windows, this is a low-risk issue. If curl is present, Rich's console capabilities should be used instead, or guard the escape codes behind a VT check.
**Warning signs:** Garbled output in legacy terminals.
**Files affected:** `downloader.py` line 174.

### Pitfall 6: benchmark.py Windows Timer Doesn't Actually Timeout
**What goes wrong:** The Windows code path in `benchmark_device()` creates `threading.Timer(timeout_sec, lambda: None)` — this timer does nothing (its callback is `lambda: None`). If XGBoost.fit() hangs on a bad GPU driver, it will hang forever.
**Why it happens:** The timer was a placeholder; on Unix, `SIGALRM` actually interrupts execution.
**How to avoid:** Use `concurrent.futures.ThreadPoolExecutor` with a timeout, or accept that the benchmark has a fixed small dataset (1000x10, 10 estimators) that should complete quickly. The risk is low since the dataset is tiny.
**Warning signs:** Benchmark hangs on Windows with a misconfigured CUDA driver.
**Files affected:** `benchmark.py` lines 66-72.

### Pitfall 7: open() Without encoding Defaults to System Encoding
**What goes wrong:** `open(path)` without `encoding=` uses `locale.getpreferredencoding()` which is cp1252 on Windows. JSON with Spanish characters will fail.
**Why it happens:** Python's default encoding is platform-dependent.
**How to avoid:** Always specify `encoding="utf-8"` on text file opens. Audit all `open()` calls.
**Warning signs:** `UnicodeDecodeError` when reading comparison JSON on Windows.
**Files affected:** `comparison.py` lines 65, 179.

## Code Examples

### Example 1: Platform Compatibility Module (`compat.py`)
```python
"""Platform compatibility utilities for Windows/Linux/macOS."""
from __future__ import annotations

import sys
import time
from pathlib import Path


def safe_rename(src: Path, dest: Path, retries: int = 3, delay: float = 0.5) -> None:
    """Rename src to dest with Windows file-locking retry."""
    for attempt in range(retries):
        try:
            if sys.platform == "win32" and dest.exists():
                dest.unlink()
            src.rename(dest)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                raise


def count_lines(path: Path) -> int:
    """Count lines in a file. Uses wc -l on Unix, pure Python fallback."""
    if sys.platform != "win32":
        import subprocess
        try:
            result = subprocess.run(
                ["wc", "-l", str(path)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return int(result.stdout.strip().split()[0])
        except (subprocess.TimeoutExpired, ValueError, IndexError, OSError):
            pass
    # Pure Python fallback (always used on Windows)
    try:
        with path.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def ensure_utf8_console() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows if needed."""
    if sys.platform != "win32":
        return
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        enc = getattr(stream, "encoding", "") or ""
        if "utf" not in enc.lower():
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, OSError):
                pass


def supports_unicode_blocks() -> bool:
    """Check if terminal supports Unicode block characters (█/░)."""
    import os
    # Windows Terminal always supports Unicode
    if os.environ.get("WT_SESSION"):
        return True
    # Check stdout encoding
    enc = getattr(sys.stdout, "encoding", "") or ""
    if "utf" in enc.lower():
        return True
    return False
```

### Example 2: nvidia-smi Windows Fallback
```python
def _has_cuda() -> bool:
    """Check for CUDA GPU via nvidia-smi with Windows path fallback."""
    nvidia_smi_paths = ["nvidia-smi"]
    if sys.platform == "win32":
        nvidia_smi_paths.append(
            r"C:\Windows\System32\nvidia-smi.exe"
        )
    for cmd in nvidia_smi_paths:
        try:
            result = subprocess.run(
                [cmd], capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False
```

### Example 3: GitHub Actions CI Matrix with Windows
```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ["3.12"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v4
      - name: Set up Python
        run: uv python install ${{ matrix.python-version }}
      - name: Install dependencies
        run: uv sync --dev
      - name: Run tests
        run: uv run pytest tests/ -v --tb=short
```

### Example 4: ASCII Fallback Sliders
```python
# Unicode block chars
_FILLED_UNICODE = "█"
_EMPTY_UNICODE = "░"
# ASCII fallback
_FILLED_ASCII = "#"
_EMPTY_ASCII = "."

def _get_bar_chars() -> tuple[str, str]:
    """Return (filled, empty) bar characters based on terminal support."""
    if supports_unicode_blocks():
        return _FILLED_UNICODE, _EMPTY_UNICODE
    return _FILLED_ASCII, _EMPTY_ASCII
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `os.path.*` everywhere | `pathlib.Path` | Already done (Phase 12) | ✅ No migration needed — already pathlib |
| `gpu_hist` tree method | `device='cuda'` + `tree_method='hist'` | XGBoost 2.0+ | ✅ Already correct in codebase |
| Windows cp1252 default | `sys.stdout.reconfigure(encoding='utf-8')` | Python 3.7+ | Must implement |
| `Path.rename()` on Windows | `safe_rename()` with retry | Pattern needed for Phase 13 | Must implement |

**Key finding:** The codebase is already in excellent shape for Windows. The `pathlib` audit will find nothing because there are zero `os.path.*` calls. The real work is in the 9 specific issues identified.

## Open Questions

1. **Joblib multiprocessing for HP search**
   - What we know: The current HP search is **sequential** — it uses a manual `for i, params in enumerate(param_samples)` loop, NOT `RandomizedSearchCV(n_jobs=N)`. The `n_jobs` parameter in `_hp_search()` is explicitly documented as "reserved for future parallel implementation." Joblib is only used for `dump()`/`load()` serialization.
   - What's unclear: Nothing — this is fully clear from the code.
   - Recommendation: No multiprocessing changes needed. The user's concern was about `RandomizedSearchCV(n_jobs=N)` which is NOT used. Document this finding clearly — HP search is sequential by design (upsampling inside CV folds prevents clean parallelization). XGBoost's internal threading (`nthread`) provides per-model parallelism and works fine on Windows. Mark `n_jobs` as used only for future reference.

2. **curl availability on Windows**
   - What we know: curl ships with Windows 10 (build 17063+, October 2018). `_curl_available()` tests for it. The requests fallback is already implemented.
   - What's unclear: Whether Windows curl supports all flags used (`--http2`, `--compressed`, etc.).
   - Recommendation: The requests fallback already works. curl on Windows 10 is typically `curl.exe` in System32 and supports HTTP/2. No action needed — existing fallback handles this.

3. **Windows benchmark timeout effectiveness**
   - What we know: The Windows timer does nothing (`lambda: None`). But the benchmark uses a tiny dataset (1000 rows, 10 features, 10 estimators) that should complete in < 1 second.
   - What's unclear: Whether a broken GPU driver could hang XGBoost.fit() indefinitely.
   - Recommendation: Replace with `concurrent.futures` timeout or accept the low risk. Recommend a simple improvement: run benchmark in a thread with `join(timeout)`.

## Concrete Issues Inventory

| # | File | Line(s) | Issue | Severity | Fix |
|---|------|---------|-------|----------|-----|
| 1 | `loaders.py` | 79 | `wc -l` fails on Windows | MEDIUM | Add Python fallback via `compat.count_lines()` |
| 2 | `downloader.py` | 220, 531 | `Path.rename()` fails if target exists on Windows | HIGH | Use `compat.safe_rename()` |
| 3 | `detector.py` | 90-95 | `nvidia-smi` not in PATH on some Windows setups | MEDIUM | Add `C:\Windows\System32\nvidia-smi.exe` fallback |
| 4 | `detector.py` | 109 | ROCm check uses `/opt/rocm` (Unix only) | LOW | Guard with `sys.platform != "win32"` |
| 5 | `downloader.py` | 174 | Raw ANSI escape codes in `_clear_lines()` | LOW | Low risk — requests fallback doesn't use this |
| 6 | `comparison.py` | 65, 179 | `open()` without `encoding='utf-8'` | MEDIUM | Add encoding parameter |
| 7 | `__main__.py` | — | No UTF-8 console init | HIGH | Call `ensure_utf8_console()` at startup |
| 8 | `config_screen.py` | 29-30 | `█`/`░` chars may not render | MEDIUM | Add ASCII fallback with detection |
| 9 | `benchmark.py` | 66-72 | Windows timer is a no-op | LOW | Low risk — tiny dataset completes fast |
| 10 | `downloader.py` | 491-503 | `signal.SIGINT` handler + curl subprocess cleanup on Windows | MEDIUM | Verify behavior, add `CREATE_NEW_PROCESS_GROUP` if needed |
| 11 | `detector.py` | 126-137 | `nvidia-smi` query for GPU name also needs Windows path fallback | MEDIUM | Same pattern as issue #3 |

## GitHub Actions CI Strategy

**Recommendation: Matrix strategy** (over separate job)

```yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, windows-latest]
```

**Rationale:**
- `fail-fast: false` ensures both OS jobs complete even if one fails
- Shared step definitions — less YAML duplication
- `uv` has official `setup-uv` GitHub Action that works on both platforms
- Tests use `tmp_path` (pytest's cross-platform temp dir) — already portable
- No platform-specific test fixtures needed

**Key CI concerns:**
- `uv sync --dev` installs all dependencies including XGBoost (has Windows wheels)
- Tests that mock `platform.system()` or `platform.machine()` already exist
- `test_system.py` marked with `@pytest.mark.system` may need data — exclude on CI with `-m "not system"`

## Sources

### Primary (HIGH confidence)
- **Codebase audit** — direct examination of all 39 Python source files
- **Python docs** — `pathlib.Path.rename()` platform behavior, `sys.stdout.reconfigure()` (Python 3.7+)
- **pyproject.toml** — confirmed `[project.scripts]` entry point, all dependency versions

### Secondary (MEDIUM confidence)
- **Windows curl** — ships with Windows 10 build 17063+ (October 2018)
- **Rich library** — handles ANSI/VT processing on Windows Terminal via built-in support
- **XGBoost** — Windows CUDA wheels available on PyPI, `nthread` parallelism works natively

### Tertiary (LOW confidence)
- **Windows nvidia-smi path** — `C:\Windows\System32\nvidia-smi.exe` is the standard location when NVIDIA drivers are installed; may vary with driver version

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project, verified Windows wheel availability
- Architecture: HIGH — compat.py pattern is proven, specific issues identified from code audit
- Pitfalls: HIGH — each issue traced to specific file and line number from codebase
- GPU detection: MEDIUM — nvidia-smi Windows path is standard but not verified on target machine
- CI strategy: HIGH — GitHub Actions `windows-latest` + `uv` is a well-documented pattern

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (stable domain — Python cross-platform patterns don't change fast)
