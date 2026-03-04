"""Download SECOP databases from datos.gov.co.

Uses the Socrata Open Data API (SODA) endpoint
(resource/{id}.csv?$limit=N) with parallel curl processes for concurrent
downloads.  Interactive progress is displayed via periodic polling of
partially-downloaded file sizes.

Features:
- Parallel downloads (configurable concurrency, default 4)
- Largest-first scheduling to minimise wall-clock time
- Stall detection (abort + retry if speed < 1 KB/s for 60 s)
- HTTP/2 and compression for throughput
- Instantaneous speed (3-second rolling window) and ETA
- Graceful Ctrl+C that preserves .part files for retry
- Post-download column validation against schemas.py
- Automatic fallback to Python requests when curl is unavailable

Usage (from CLI):
    python -m sip_engine download-data                    # all 8 datasets
    python -m sip_engine download-data --dataset contratos procesos
    python -m sip_engine download-data --dry-run          # show URLs only
    python -m sip_engine download-data --resume           # retry failed ones
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import requests  # Fallback when curl is not available

from sip_engine.compat import safe_rename
from sip_engine.config import get_settings

# ── Dataset registry ─────────────────────────────────────────────────────────

# Approximate sizes in bytes (used for ETA estimation and sorting).
# Updated periodically — not used for correctness, only UX.
_APPROX_SIZES: dict[str, int] = {
    "contratos": 9_400_000_000,
    "procesos": 9_800_000_000,
    "ofertas": 7_500_000_000,
    "proponentes": 586_000_000,
    "proveedores": 585_000_000,
    "ejecucion": 926_000_000,
    "adiciones": 3_900_000_000,
    "suspensiones": 114_000_000,
    "rues": 197_000_000,
}


@dataclass(frozen=True)
class SECOPDataset:
    """Metadata for a single datos.gov.co SECOP II dataset."""

    key: str               # CLI-friendly short name
    api_id: str            # datos.gov.co 4x4 identifier
    filename: str          # target filename inside secop_dir
    description: str       # human-readable name

    # Maximum rows to request from the SODA API.  Must exceed the largest
    # dataset (adiciones ≈ 15.8 M rows as of 2025-02).
    _SODA_LIMIT: int = 50_000_000

    @property
    def url(self) -> str:
        return (
            f"https://www.datos.gov.co/resource/{self.api_id}"
            f".csv?$limit={self._SODA_LIMIT}"
        )

    @property
    def approx_bytes(self) -> int:
        return _APPROX_SIZES.get(self.key, 0)


DATASETS: tuple[SECOPDataset, ...] = (
    SECOPDataset(
        key="contratos",
        api_id="jbjy-vk9h",
        filename="contratos_SECOP.csv",
        description="SECOP II – Contratos Electrónicos",
    ),
    SECOPDataset(
        key="procesos",
        api_id="p6dx-8zbt",
        filename="procesos_SECOP.csv",
        description="SECOP II – Procesos de Compra",
    ),
    SECOPDataset(
        key="ofertas",
        api_id="wi7w-2nvm",
        filename="ofertas_proceso_SECOP.csv",
        description="SECOP II – Ofertas",
    ),
    SECOPDataset(
        key="proponentes",
        api_id="hgi6-6wh3",
        filename="proponentes_proceso_SECOP.csv",
        description="SECOP II – Proponentes",
    ),
    SECOPDataset(
        key="proveedores",
        api_id="qmzu-gj57",
        filename="proveedores_registrados.csv",
        description="SECOP II – Proveedores Registrados",
    ),
    SECOPDataset(
        key="ejecucion",
        api_id="mfmm-jqmq",
        filename="ejecucion_contratos.csv",
        description="SECOP II – Ejecución Contratos",
    ),
    SECOPDataset(
        key="adiciones",
        api_id="cb9c-h8sn",
        filename="adiciones.csv",
        description="SECOP II – Adiciones",
    ),
    SECOPDataset(
        key="suspensiones",
        api_id="u99c-7mfm",
        filename="suspensiones_contratos.csv",
        description="SECOP II – Suspensiones de Contratos",
    ),
    SECOPDataset(
        key="rues",
        api_id="c82u-588k",
        filename="rues_personas.csv",
        description="RUES – Personas Naturales, Jurídicas y ESADL (CONFECAMARAS)",
    ),
)

DATASET_BY_KEY: dict[str, SECOPDataset] = {d.key: d for d in DATASETS}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_size(nbytes: float) -> str:
    """Format bytes into human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:,.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:,.1f} TB"


def _fmt_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 0 or seconds > 86400 * 7:
        return "—"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h{m:02d}m"
    if m > 0:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def _term_width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def _clear_lines(n: int) -> None:
    """Move cursor up n lines and clear them.

    Uses ANSI VT100 escape sequences — works in Windows Terminal;
    the requests fallback path (primary on Windows) does not use this.
    """
    for _ in range(n):
        sys.stdout.write("\033[A\033[2K")
    sys.stdout.flush()


# ── Core download logic ──────────────────────────────────────────────────────

def _curl_available() -> bool:
    """Check if curl is installed and callable."""
    try:
        result = subprocess.run(
            ["curl", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _download_with_requests(
    datasets: list[SECOPDataset],
    output_dir: Path,
    succeeded: list[Path],
) -> list[Path]:
    """Sequential download fallback using Python requests (no curl needed).

    Simpler than the parallel curl path but fully functional.  Used
    automatically on Windows or any system where curl is not installed.
    """
    for ds in datasets:
        target = output_dir / ds.filename
        tmp = target.with_suffix(".csv.part")
        print(f"  ⟳  Downloading {ds.key} ({ds.description})...")
        try:
            response = requests.get(ds.url, stream=True, timeout=600)
            response.raise_for_status()
            downloaded = 0
            with tmp.open("wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        # Print progress every ~10 MB
                        if downloaded % (10 * 1024 * 1024) < 65536:
                            print(f"\r    {_fmt_size(downloaded)}", end="", flush=True)
            print(f"\r  ✓  {ds.key:<16} {_fmt_size(downloaded)}")
            safe_rename(tmp, target)
            succeeded.append(target)
        except KeyboardInterrupt:
            print(f"\n  ⚠  Download interrupted. Partial file preserved: {tmp}")
            break
        except Exception as e:
            print(f"\r  ✗  {ds.key:<16} {e}")
    return succeeded


# Rolling window size for instantaneous speed calculation
_SPEED_WINDOW_SECONDS = 3.0


@dataclass
class _DownloadSlot:
    """Tracks one active curl download."""

    dataset: SECOPDataset
    target: Path           # final destination
    tmp: Path              # temporary download path (.part)
    proc: subprocess.Popen  # curl process
    started: float         # time.monotonic() at launch
    # Rolling speed window: deque of (timestamp, cumulative_bytes)
    size_samples: deque = field(default_factory=lambda: deque(maxlen=10))

    def instantaneous_speed(self) -> float:
        """Return bytes/sec over the last ~3 seconds."""
        if len(self.size_samples) < 2:
            return 0.0
        newest_t, newest_b = self.size_samples[-1]
        # Find the oldest sample within the window
        oldest_t, oldest_b = self.size_samples[0]
        for t, b in self.size_samples:
            if newest_t - t <= _SPEED_WINDOW_SECONDS:
                oldest_t, oldest_b = t, b
                break
        dt = newest_t - oldest_t
        if dt <= 0:
            return 0.0
        return (newest_b - oldest_b) / dt

    def record_size(self, size: int) -> None:
        self.size_samples.append((time.monotonic(), size))


def _launch_curl(
    ds: SECOPDataset, output_dir: Path, *, resume: bool = False
) -> _DownloadSlot:
    """Start a curl process for one dataset."""
    target = output_dir / ds.filename
    tmp = target.with_suffix(".csv.part")

    cmd = [
        "curl",
        "--silent",                # suppress default progress
        "--show-error",            # still show errors
        "--fail",                  # fail on HTTP errors
        "--location",              # follow redirects
        "--compressed",            # request gzip/deflate from server
        "--http2",                 # prefer HTTP/2 for better throughput
        "--keepalive-time", "60",  # keep TCP connections alive
        "--retry", "3",
        "--retry-delay", "5",
        "--retry-max-time", "120",
        "--connect-timeout", "30",
        "--speed-limit", "1000",   # stall watchdog: min 1 KB/s ...
        "--speed-time", "60",      # ... for 60 seconds before aborting
        "--output", str(tmp),
    ]

    # NOTE: --continue-at is incompatible with the SODA API (dynamic
    # response, no Content-Range support).  On resume we simply re-download
    # from scratch and overwrite the .part file.
    if resume and tmp.exists() and tmp.stat().st_size > 0:
        pass  # .part will be overwritten by --output

    cmd.append(ds.url)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    slot = _DownloadSlot(
        dataset=ds,
        target=target,
        tmp=tmp,
        proc=proc,
        started=time.monotonic(),
    )
    # Seed with initial size if resuming
    if resume and tmp.exists():
        slot.record_size(tmp.stat().st_size)
    else:
        slot.record_size(0)
    return slot


def _render_progress(
    slots: list[_DownloadSlot],
    finished: list[tuple[SECOPDataset, float, float, bool]],  # (ds, size, elapsed, ok)
    total_count: int,
) -> int:
    """Print a live progress table.  Returns number of lines printed."""
    width = _term_width()
    lines: list[str] = []

    header = f"  Downloading {total_count} SECOP datasets from datos.gov.co"
    lines.append(header)
    lines.append("─" * min(width, 78))

    # Finished downloads
    for ds, size, elapsed, ok in finished:
        status = "✓" if ok else "✗"
        elapsed_str = _fmt_duration(elapsed)
        avg_speed = _fmt_size(size / elapsed) + "/s" if elapsed > 0 and ok else ""
        label = f"done in {elapsed_str}  {avg_speed}" if ok else "FAILED"
        lines.append(f"  {status}  {ds.key:<16} {_fmt_size(size):>12}   {label}")

    # Active downloads
    for slot in slots:
        try:
            current_size = slot.tmp.stat().st_size if slot.tmp.exists() else 0
        except OSError:
            current_size = 0
        slot.record_size(current_size)

        speed = slot.instantaneous_speed()
        speed_str = f"{_fmt_size(speed)}/s" if speed > 100 else "starting…"

        # ETA based on approximate known size
        eta_str = ""
        approx = slot.dataset.approx_bytes
        if approx > 0 and speed > 100 and current_size < approx:
            remaining = approx - current_size
            eta_str = f"  ETA {_fmt_duration(remaining / speed)}"
        # Progress percentage
        pct_str = ""
        if approx > 0 and current_size > 0:
            pct = min(current_size / approx * 100, 99.9)
            pct_str = f"  {pct:4.1f}%"

        lines.append(
            f"  ⟳  {slot.dataset.key:<16} {_fmt_size(current_size):>12}   "
            f"{speed_str}{pct_str}{eta_str}"
        )

    # Pending count
    pending = total_count - len(finished) - len(slots)
    if pending > 0:
        lines.append(f"  …  {pending} more queued")

    lines.append("─" * min(width, 78))

    for line in lines:
        sys.stdout.write(line + "\n")
    sys.stdout.flush()
    return len(lines)


def _sort_largest_first(datasets: list[SECOPDataset]) -> list[SECOPDataset]:
    """Sort datasets largest-first to minimise total wall-clock time."""
    return sorted(datasets, key=lambda d: d.approx_bytes, reverse=True)


def download_datasets(
    datasets: Sequence[SECOPDataset] | None = None,
    output_dir: Path | None = None,
    parallel: int = 4,
    dry_run: bool = False,
    skip_existing: bool = False,
    resume: bool = False,
) -> list[Path]:
    """Download SECOP datasets from datos.gov.co using parallel curl.

    Args:
        datasets: Which datasets to download (default: all 8).
        output_dir: Destination directory (default: Settings.secop_dir).
        parallel: Max concurrent curl processes (default: 4).
        dry_run: If True, print URLs and exit without downloading.
        skip_existing: If True, skip datasets whose target file already exists.
        resume: If True, resume partially downloaded .part files.

    Returns:
        List of paths to successfully downloaded CSV files.
    """
    if datasets is None:
        datasets = list(DATASETS)
    if output_dir is None:
        output_dir = get_settings().secop_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Dry-run mode ──────────────────────────────────────────────────
    if dry_run:
        print(f"\n  Dry run — would download {len(datasets)} datasets to {output_dir}\n")
        for ds in datasets:
            existing = output_dir / ds.filename
            part = existing.with_suffix(".csv.part")
            notes: list[str] = []
            if existing.exists():
                notes.append(f"exists: {_fmt_size(existing.stat().st_size)}")
            if part.exists():
                notes.append(f"partial: {_fmt_size(part.stat().st_size)}")
            note_str = f"  ({', '.join(notes)})" if notes else ""
            print(f"  {ds.key:<16}  {ds.url}")
            print(f"  {'':16}  → {ds.filename}{note_str}")
        print()
        return []

    # ── Filter out existing if requested ──────────────────────────────
    if skip_existing:
        filtered = []
        for ds in datasets:
            if (output_dir / ds.filename).exists():
                print(f"  ⊘  {ds.key:<16} already exists, skipping")
            else:
                filtered.append(ds)
        datasets = filtered
        if not datasets:
            print("\n  All datasets already present. Nothing to download.\n")
            return []

    # ── Sort largest-first for optimal scheduling ─────────────────────
    datasets = _sort_largest_first(list(datasets))

    # ── Show resume info ──────────────────────────────────────────────
    if resume:
        for ds in datasets:
            part = (output_dir / ds.filename).with_suffix(".csv.part")
            if part.exists() and part.stat().st_size > 0:
                print(f"  ↻  {ds.key:<16} resuming from {_fmt_size(part.stat().st_size)}")

    # ── Confirm before downloading ────────────────────────────────────
    total_approx = sum(ds.approx_bytes for ds in datasets)
    print(f"\n  Will download {len(datasets)} datasets to {output_dir}")
    print(f"  Estimated total: ~{_fmt_size(total_approx)}")
    print(f"  Parallel connections: {parallel}")
    print(f"  Resume mode: {'on' if resume else 'off'}\n")
    for ds in datasets:
        print(f"    • {ds.description}  ({ds.filename}, ~{_fmt_size(ds.approx_bytes)})")
    print()

    try:
        answer = input("  Proceed? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Aborted.")
        return []
    if answer and answer not in ("y", "yes", "si", "sí"):
        print("  Aborted.")
        return []
    print()

    # ── Check curl availability; fall back to requests if missing ─────
    use_curl = _curl_available()
    if not use_curl:
        print("  ℹ  curl not found — using Python requests library (slower, no HTTP/2)")
        succeeded: list[Path] = []
        return _download_with_requests(list(datasets), output_dir, succeeded)

    # ── Run parallel downloads with live progress ─────────────────────
    queue = list(datasets)
    active: list[_DownloadSlot] = []
    finished: list[tuple[SECOPDataset, float, float, bool]] = []
    succeeded: list[Path] = []
    total = len(queue)
    prev_lines = 0
    interrupted = False

    # Graceful Ctrl+C handler: terminate curl processes, keep .part files
    original_sigint = signal.getsignal(signal.SIGINT)

    def _sigint_handler(signum, frame):
        nonlocal interrupted
        interrupted = True
        # Terminate active curl processes gracefully
        for slot in active:
            try:
                slot.proc.terminate()
            except OSError:
                pass

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        while (queue or active) and not interrupted:
            # Fill up to `parallel` slots
            while queue and len(active) < parallel:
                ds = queue.pop(0)
                active.append(_launch_curl(ds, output_dir, resume=resume))

            # Render progress
            if prev_lines > 0:
                _clear_lines(prev_lines)
            prev_lines = _render_progress(active, finished, total)

            # Check for completed processes
            still_active: list[_DownloadSlot] = []
            for slot in active:
                retcode = slot.proc.poll()
                if retcode is None:
                    still_active.append(slot)
                    continue

                # Process finished
                elapsed = time.monotonic() - slot.started
                ok = retcode == 0
                size = 0.0
                if ok and slot.tmp.exists():
                    size = slot.tmp.stat().st_size
                    safe_rename(slot.tmp, slot.target)
                    succeeded.append(slot.target)
                elif not ok:
                    stderr_msg = ""
                    if slot.proc.stderr:
                        stderr_msg = slot.proc.stderr.read().decode(errors="replace").strip()
                    # Keep .part file for resume — don't delete it
                    part_size = slot.tmp.stat().st_size if slot.tmp.exists() else 0
                    size = part_size
                    if stderr_msg:
                        sys.stdout.write(
                            f"\r  ✗  {slot.dataset.key}: curl exit {retcode} — {stderr_msg}\n"
                        )

                finished.append((slot.dataset, size, elapsed, ok))

            active = still_active
            if active:
                time.sleep(1.0)

    finally:
        signal.signal(signal.SIGINT, original_sigint)

    # ── Final render ──────────────────────────────────────────────────
    if prev_lines > 0:
        _clear_lines(prev_lines)
    _render_progress([], finished, total)

    if interrupted:
        # Show resume hint
        part_files = [
            (ds.key, (output_dir / ds.filename).with_suffix(".csv.part"))
            for ds in datasets
        ]
        parts_present = [(k, p) for k, p in part_files if p.exists() and p.stat().st_size > 0]
        print(f"\n  ⚠  Download interrupted. {len(parts_present)} partial file(s) preserved.")
        if parts_present:
            print("  To resume, run:")
            print("    python -m sip_engine download-data --resume")
        print()
        return succeeded

    ok_count = sum(1 for _, _, _, ok in finished if ok)
    fail_count = total - ok_count
    total_bytes = sum(sz for _, sz, _, ok in finished if ok)

    print(f"\n  Done: {ok_count}/{total} succeeded ({_fmt_size(total_bytes)} total)")
    if fail_count:
        print(f"  ⚠  {fail_count} download(s) failed — .part files preserved for --resume")
    print()

    return succeeded


def validate_downloads(output_dir: Path | None = None) -> None:
    """Validate downloaded CSVs against schema column expectations.

    Reads only the header row of each file and checks that all columns
    required by schemas.py are present.
    """
    from sip_engine.data.schemas import (
        ADICIONES_USECOLS,
        CONTRATOS_USECOLS,
        EJECUCION_USECOLS,
        OFERTAS_USECOLS,
        PROCESOS_USECOLS,
        PROPONENTES_USECOLS,
        PROVEEDORES_USECOLS,
        SUSPENSIONES_USECOLS,
        validate_columns,
    )

    if output_dir is None:
        output_dir = get_settings().secop_dir

    checks: list[tuple[str, str, list]] = [
        ("contratos", "contratos_SECOP.csv", CONTRATOS_USECOLS),
        ("procesos", "procesos_SECOP.csv", PROCESOS_USECOLS),
        ("ofertas", "ofertas_proceso_SECOP.csv", OFERTAS_USECOLS),
        ("proponentes", "proponentes_proceso_SECOP.csv", PROPONENTES_USECOLS),
        ("proveedores", "proveedores_registrados.csv", PROVEEDORES_USECOLS),
        ("ejecucion", "ejecucion_contratos.csv", EJECUCION_USECOLS),
        ("adiciones", "adiciones.csv", ADICIONES_USECOLS),
        ("suspensiones", "suspensiones_contratos.csv", SUSPENSIONES_USECOLS),
    ]

    print(f"\n  Validating columns in {output_dir}\n")
    all_ok = True
    for key, fname, usecols in checks:
        path = output_dir / fname
        if not path.exists():
            print(f"  ⊘  {key:<16}  not found, skipping")
            continue
        try:
            validate_columns(str(path), usecols)
            print(f"  ✓  {key:<16}  all {len(usecols)} required columns present")
        except ValueError as e:
            print(f"  ✗  {key:<16}  {e}")
            all_ok = False

    status = "All validations passed ✓" if all_ok else "Some validations failed ✗"
    print(f"\n  {status}\n")
