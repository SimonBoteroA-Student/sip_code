"""Unit tests for the platform compatibility module (sip_engine.compat).

Covers all four exported functions with both happy-path and edge-case
scenarios, using ``unittest.mock.patch`` for platform/env mocking and
``tmp_path`` (pytest fixture) for all file-based tests.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sip_engine.compat import (
    count_lines,
    ensure_utf8_console,
    safe_rename,
    supports_unicode_blocks,
)


# ---------------------------------------------------------------------------
# safe_rename
# ---------------------------------------------------------------------------


class TestSafeRename:
    """Tests for safe_rename()."""

    def test_basic(self, tmp_path: Path) -> None:
        """Rename a file to a non-existing target — should just work."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("hello", encoding="utf-8")

        safe_rename(src, dst)

        assert not src.exists()
        assert dst.read_text(encoding="utf-8") == "hello"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        """On Windows, if dest exists, safe_rename removes it before renaming."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("new-content", encoding="utf-8")
        dst.write_text("old-content", encoding="utf-8")

        safe_rename(src, dst)

        assert not src.exists()
        assert dst.read_text(encoding="utf-8") == "new-content"

    def test_permission_error_retries(self, tmp_path: Path) -> None:
        """PermissionError triggers retry with back-off; succeeds on 3rd attempt."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("data", encoding="utf-8")

        call_count = 0
        original_rename = Path.rename

        def _flaky_rename(self_path, target):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise PermissionError("File in use")
            return original_rename(self_path, target)

        with patch.object(Path, "rename", _flaky_rename):
            safe_rename(src, dst, retries=3, delay=0.01)

        assert call_count == 3
        assert dst.read_text(encoding="utf-8") == "data"

    def test_permission_error_exhausted(self, tmp_path: Path) -> None:
        """After all retries exhausted, PermissionError is re-raised."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("data", encoding="utf-8")

        def _always_fail(self_path, target):
            raise PermissionError("Locked forever")

        with patch.object(Path, "rename", _always_fail):
            with pytest.raises(PermissionError, match="Locked forever"):
                safe_rename(src, dst, retries=2, delay=0.01)


# ---------------------------------------------------------------------------
# count_lines
# ---------------------------------------------------------------------------


class TestCountLines:
    """Tests for count_lines()."""

    def test_pure_python_fallback(self, tmp_path: Path) -> None:
        """On Windows (mocked), the pure-Python fallback counts correctly."""
        f = tmp_path / "five_lines.txt"
        f.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

        with patch("sip_engine.compat.sys") as mock_sys:
            mock_sys.platform = "win32"
            # Re-import to get the patched version — or just call directly
            # since count_lines checks sys.platform at call time
            from sip_engine.compat import count_lines as cl

            assert cl(f) == 5

    def test_empty_file(self, tmp_path: Path) -> None:
        """An empty file should return 0."""
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        assert count_lines(f) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """A missing file returns 0 (OSError caught)."""
        missing = tmp_path / "no_such_file.txt"
        # Force Windows path to use pure-Python fallback
        with patch("sip_engine.compat.sys") as mock_sys:
            mock_sys.platform = "win32"
            from sip_engine.compat import count_lines as cl

            assert cl(missing) == 0

    def test_multiline_no_trailing_newline(self, tmp_path: Path) -> None:
        """Lines without a trailing newline are still counted."""
        f = tmp_path / "no_newline.txt"
        f.write_text("line1\nline2\nline3", encoding="utf-8")
        # Pure-Python binary-read counts 3 lines
        with patch("sip_engine.compat.sys") as mock_sys:
            mock_sys.platform = "win32"
            from sip_engine.compat import count_lines as cl

            assert cl(f) == 3


# ---------------------------------------------------------------------------
# ensure_utf8_console
# ---------------------------------------------------------------------------


class TestEnsureUtf8Console:
    """Tests for ensure_utf8_console()."""

    def test_noop_on_unix(self) -> None:
        """On Linux the function is a no-op — stdout is not reconfigured."""
        mock_stdout = MagicMock()
        mock_stdout.encoding = "cp1252"

        with patch("sip_engine.compat.sys") as mock_sys:
            mock_sys.platform = "linux"
            mock_sys.stdout = mock_stdout
            mock_sys.stderr = MagicMock()

            ensure_utf8_console()

            mock_stdout.reconfigure.assert_not_called()

    def test_reconfigures_on_windows_cp1252(self) -> None:
        """On Windows with cp1252, stdout+stderr should be reconfigured."""
        mock_stdout = MagicMock()
        mock_stdout.encoding = "cp1252"
        mock_stderr = MagicMock()
        mock_stderr.encoding = "cp1252"

        with patch("sip_engine.compat.sys") as mock_sys:
            mock_sys.platform = "win32"
            mock_sys.stdout = mock_stdout
            mock_sys.stderr = mock_stderr

            # Need to use getattr on mock_sys
            def _getattr_side_effect(name):
                if name == "stdout":
                    return mock_stdout
                if name == "stderr":
                    return mock_stderr
                raise AttributeError(name)

            ensure_utf8_console()

            mock_stdout.reconfigure.assert_called_once_with(encoding="utf-8")
            mock_stderr.reconfigure.assert_called_once_with(encoding="utf-8")

    def test_skips_if_already_utf8(self) -> None:
        """On Windows with UTF-8 encoding, no reconfiguration needed."""
        mock_stdout = MagicMock()
        mock_stdout.encoding = "utf-8"
        mock_stderr = MagicMock()
        mock_stderr.encoding = "utf-8"

        with patch("sip_engine.compat.sys") as mock_sys:
            mock_sys.platform = "win32"
            mock_sys.stdout = mock_stdout
            mock_sys.stderr = mock_stderr

            ensure_utf8_console()

            mock_stdout.reconfigure.assert_not_called()
            mock_stderr.reconfigure.assert_not_called()


# ---------------------------------------------------------------------------
# supports_unicode_blocks
# ---------------------------------------------------------------------------


class TestSupportsUnicodeBlocks:
    """Tests for supports_unicode_blocks()."""

    def test_wt_session_env(self) -> None:
        """Windows Terminal sets WT_SESSION → should return True."""
        with patch.dict("os.environ", {"WT_SESSION": "some-guid"}):
            assert supports_unicode_blocks() is True

    def test_utf8_encoding(self) -> None:
        """stdout encoding containing 'utf' → should return True."""
        mock_stdout = MagicMock()
        mock_stdout.encoding = "utf-8"
        with patch.dict("os.environ", {}, clear=True), patch(
            "sip_engine.compat.sys"
        ) as mock_sys:
            mock_sys.stdout = mock_stdout
            assert supports_unicode_blocks() is True

    def test_cp1252_no_wt(self) -> None:
        """cp1252 encoding without WT_SESSION → should return False."""
        mock_stdout = MagicMock()
        mock_stdout.encoding = "cp1252"
        env = {k: v for k, v in __import__("os").environ.items() if k != "WT_SESSION"}
        with patch.dict("os.environ", env, clear=True), patch(
            "sip_engine.compat.sys"
        ) as mock_sys:
            mock_sys.stdout = mock_stdout
            assert supports_unicode_blocks() is False

    def test_none_encoding_no_wt(self) -> None:
        """None encoding without WT_SESSION → should return False."""
        mock_stdout = MagicMock()
        mock_stdout.encoding = None
        env = {k: v for k, v in __import__("os").environ.items() if k != "WT_SESSION"}
        with patch.dict("os.environ", env, clear=True), patch(
            "sip_engine.compat.sys"
        ) as mock_sys:
            mock_sys.stdout = mock_stdout
            assert supports_unicode_blocks() is False
