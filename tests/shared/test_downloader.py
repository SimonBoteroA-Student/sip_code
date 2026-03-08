"""Tests for paginated SODA API downloader.

Tests:
- SECOPDataset.page_url: correct URL generation with offset/limit
- _count_csv_data_rows: data row counting (header excluded)
- _append_page: header handling across paginated pages
- _download_with_requests: paginated download via mocked requests
- Curl pagination loop: page completion → next page or done
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sip_engine.shared.data.downloader import (
    SECOPDataset,
    _SODA_PAGE_SIZE,
    _DownloadSlot,
    _append_page,
    _count_csv_data_rows,
    _download_with_requests,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_dataset():
    return SECOPDataset(
        key="test",
        api_id="abcd-1234",
        filename="test_data.csv",
        description="Test Dataset",
    )


@pytest.fixture
def output_dir(tmp_path):
    d = tmp_path / "downloads"
    d.mkdir()
    return d


# ── SECOPDataset.page_url ────────────────────────────────────────────────────

class TestPageUrl:
    def test_default_offset(self, sample_dataset):
        url = sample_dataset.page_url()
        assert "abcd-1234" in url
        assert "$limit=50000" in url
        assert "$offset=0" in url

    def test_custom_offset(self, sample_dataset):
        url = sample_dataset.page_url(offset=100000)
        assert "$offset=100000" in url
        assert "$limit=50000" in url

    def test_custom_limit(self, sample_dataset):
        url = sample_dataset.page_url(offset=0, limit=10)
        assert "$limit=10" in url
        assert "$offset=0" in url

    def test_base_url_property(self, sample_dataset):
        """The .url property should be the base URL without limit/offset."""
        assert sample_dataset.url == "https://www.datos.gov.co/resource/abcd-1234.csv"
        assert "$limit" not in sample_dataset.url


# ── _count_csv_data_rows ─────────────────────────────────────────────────────

class TestCountCsvDataRows:
    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.csv"
        f.write_bytes(b"")
        assert _count_csv_data_rows(f) == 0

    def test_header_only(self, tmp_path):
        f = tmp_path / "header.csv"
        f.write_bytes(b"col1,col2,col3\n")
        assert _count_csv_data_rows(f) == 0

    def test_header_plus_rows(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_bytes(b"col1,col2\nA,1\nB,2\nC,3\n")
        assert _count_csv_data_rows(f) == 3

    def test_no_trailing_newline(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_bytes(b"col1,col2\nA,1\nB,2")
        assert _count_csv_data_rows(f) == 2

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "missing.csv"
        assert _count_csv_data_rows(f) == 0


# ── _append_page ─────────────────────────────────────────────────────────────

class TestAppendPage:
    def _make_slot(self, output_dir, sample_dataset, page_count=0):
        target = output_dir / sample_dataset.filename
        part = target.with_suffix(".csv.part")
        page_tmp = target.with_suffix(".csv.page")
        proc = MagicMock()
        return _DownloadSlot(
            dataset=sample_dataset,
            target=target,
            part=part,
            page_tmp=page_tmp,
            proc=proc,
            started=0.0,
            offset=page_count * _SODA_PAGE_SIZE,
            page_count=page_count,
        )

    def test_first_page_keeps_header(self, output_dir, sample_dataset):
        slot = self._make_slot(output_dir, sample_dataset, page_count=0)
        slot.page_tmp.write_bytes(b"col1,col2\nA,1\nB,2\nC,3\n")

        rows = _append_page(slot)

        assert rows == 3
        content = slot.part.read_bytes()
        assert content == b"col1,col2\nA,1\nB,2\nC,3\n"
        assert not slot.page_tmp.exists()  # cleaned up

    def test_subsequent_page_strips_header(self, output_dir, sample_dataset):
        slot = self._make_slot(output_dir, sample_dataset, page_count=0)
        # Write first page
        slot.page_tmp.write_bytes(b"col1,col2\nA,1\nB,2\n")
        _append_page(slot)
        slot.page_count = 1

        # Write second page (header should be stripped)
        slot.page_tmp.write_bytes(b"col1,col2\nC,3\nD,4\n")
        rows = _append_page(slot)

        assert rows == 2
        content = slot.part.read_bytes()
        assert content == b"col1,col2\nA,1\nB,2\nC,3\nD,4\n"

    def test_three_pages(self, output_dir, sample_dataset):
        slot = self._make_slot(output_dir, sample_dataset, page_count=0)

        # Page 0
        slot.page_tmp.write_bytes(b"h1,h2\nr1\n")
        rows0 = _append_page(slot)
        assert rows0 == 1
        slot.page_count = 1

        # Page 1
        slot.page_tmp.write_bytes(b"h1,h2\nr2\nr3\n")
        rows1 = _append_page(slot)
        assert rows1 == 2
        slot.page_count = 2

        # Page 2
        slot.page_tmp.write_bytes(b"h1,h2\nr4\n")
        rows2 = _append_page(slot)
        assert rows2 == 1

        content = slot.part.read_bytes()
        assert content == b"h1,h2\nr1\nr2\nr3\nr4\n"

    def test_empty_page(self, output_dir, sample_dataset):
        slot = self._make_slot(output_dir, sample_dataset, page_count=0)
        slot.page_tmp.write_bytes(b"")
        rows = _append_page(slot)
        assert rows == 0

    def test_header_only_page(self, output_dir, sample_dataset):
        """A page with only a header (no data) returns 0 rows."""
        slot = self._make_slot(output_dir, sample_dataset, page_count=1)
        # Simulate first page already written
        slot.part.write_bytes(b"col1\nA\n")
        slot.page_tmp.write_bytes(b"col1\n")
        rows = _append_page(slot)
        assert rows == 0
        # Original data preserved, no extra data appended
        assert slot.part.read_bytes() == b"col1\nA\n"

    def test_page_tmp_missing(self, output_dir, sample_dataset):
        slot = self._make_slot(output_dir, sample_dataset, page_count=0)
        # Don't create page_tmp at all
        rows = _append_page(slot)
        assert rows == 0


# ── _download_with_requests (paginated) ──────────────────────────────────────

class TestDownloadWithRequests:
    def test_single_page_dataset(self, output_dir, sample_dataset):
        """Dataset that fits in one page (fewer rows than PAGE_SIZE)."""
        csv_content = b"col1,col2\nA,1\nB,2\n"

        mock_response = MagicMock()
        mock_response.content = csv_content
        mock_response.raise_for_status = MagicMock()

        succeeded: list[Path] = []
        with patch("sip_engine.shared.data.downloader.requests.get", return_value=mock_response):
            result = _download_with_requests([sample_dataset], output_dir, succeeded)

        assert len(result) == 1
        target = output_dir / sample_dataset.filename
        assert target.exists()
        assert target.read_bytes() == csv_content

    def test_multi_page_dataset(self, output_dir, sample_dataset):
        """Dataset that requires multiple pages."""
        header = b"col1,col2\n"
        # Build pages: page 0 has PAGE_SIZE rows, page 1 has 2 rows (< PAGE_SIZE → last page)
        page0_rows = b"".join(f"val{i},data{i}\n".encode() for i in range(_SODA_PAGE_SIZE))
        page0 = header + page0_rows

        page1 = b"col1,col2\nX,last1\nY,last2\n"

        call_count = 0

        def mock_get(url, **kwargs):
            nonlocal call_count
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if call_count == 0:
                resp.content = page0
            else:
                resp.content = page1
            call_count += 1
            return resp

        succeeded: list[Path] = []
        with patch("sip_engine.shared.data.downloader.requests.get", side_effect=mock_get):
            result = _download_with_requests([sample_dataset], output_dir, succeeded)

        assert len(result) == 1
        assert call_count == 2
        target = output_dir / sample_dataset.filename
        content = target.read_bytes()
        # Should have header once, then all data rows
        lines = content.split(b"\n")
        while lines and lines[-1] == b"":
            lines.pop()
        assert lines[0] == b"col1,col2"
        # PAGE_SIZE rows from page 0 + 2 rows from page 1
        assert len(lines) - 1 == _SODA_PAGE_SIZE + 2

    def test_requests_correct_urls(self, output_dir, sample_dataset):
        """Verify requests are made with correct paginated URLs."""
        urls_called = []

        def mock_get(url, **kwargs):
            urls_called.append(url)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.content = b"col1\ndata\n"  # 1 row < PAGE_SIZE → stops
            return resp

        succeeded: list[Path] = []
        with patch("sip_engine.shared.data.downloader.requests.get", side_effect=mock_get):
            _download_with_requests([sample_dataset], output_dir, succeeded)

        assert len(urls_called) == 1
        assert "$offset=0" in urls_called[0]
        assert f"$limit={_SODA_PAGE_SIZE}" in urls_called[0]

    def test_multi_page_correct_offsets(self, output_dir, sample_dataset):
        """Verify offset increments correctly across pages."""
        urls_called = []
        call_count = 0

        def mock_get(url, **kwargs):
            nonlocal call_count
            urls_called.append(url)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            header = b"col1\n"
            if call_count < 2:
                # Full pages
                rows = b"".join(b"x\n" for _ in range(_SODA_PAGE_SIZE))
                resp.content = header + rows
            else:
                # Last page (partial)
                resp.content = b"col1\nfinal\n"
            call_count += 1
            return resp

        succeeded: list[Path] = []
        with patch("sip_engine.shared.data.downloader.requests.get", side_effect=mock_get):
            _download_with_requests([sample_dataset], output_dir, succeeded)

        assert len(urls_called) == 3
        assert "$offset=0" in urls_called[0]
        assert f"$offset={_SODA_PAGE_SIZE}" in urls_called[1]
        assert f"$offset={_SODA_PAGE_SIZE * 2}" in urls_called[2]


# ── Curl pagination flow ─────────────────────────────────────────────────────

class TestCurlPaginationFlow:
    """Test the page-level logic without actually launching curl."""

    def test_append_page_then_check_completion(self, output_dir, sample_dataset):
        """Simulate the main loop's page completion logic."""
        slot = _DownloadSlot(
            dataset=sample_dataset,
            target=output_dir / sample_dataset.filename,
            part=(output_dir / sample_dataset.filename).with_suffix(".csv.part"),
            page_tmp=(output_dir / sample_dataset.filename).with_suffix(".csv.page"),
            proc=MagicMock(),
            started=0.0,
            offset=0,
            page_count=0,
        )

        # Simulate page 0 with fewer than PAGE_SIZE rows → dataset done
        slot.page_tmp.write_bytes(b"h1,h2\nrow1\nrow2\n")
        data_rows = _append_page(slot)
        slot.page_count += 1

        assert data_rows == 2
        assert data_rows < _SODA_PAGE_SIZE  # should be considered done

    def test_full_page_triggers_next(self, output_dir, sample_dataset):
        """A full page (PAGE_SIZE rows) should trigger next page fetch."""
        slot = _DownloadSlot(
            dataset=sample_dataset,
            target=output_dir / sample_dataset.filename,
            part=(output_dir / sample_dataset.filename).with_suffix(".csv.part"),
            page_tmp=(output_dir / sample_dataset.filename).with_suffix(".csv.page"),
            proc=MagicMock(),
            started=0.0,
            offset=0,
            page_count=0,
        )

        # Build a page with exactly PAGE_SIZE data rows
        header = b"col1\n"
        rows = b"".join(b"x\n" for _ in range(_SODA_PAGE_SIZE))
        slot.page_tmp.write_bytes(header + rows)

        data_rows = _append_page(slot)
        slot.page_count += 1

        assert data_rows == _SODA_PAGE_SIZE  # should trigger next page
        # Verify offset would be incremented
        slot.offset += _SODA_PAGE_SIZE
        assert slot.offset == _SODA_PAGE_SIZE

    def test_current_size_combines_part_and_page(self, output_dir, sample_dataset):
        """current_size() should sum .part and .page file sizes."""
        slot = _DownloadSlot(
            dataset=sample_dataset,
            target=output_dir / sample_dataset.filename,
            part=(output_dir / sample_dataset.filename).with_suffix(".csv.part"),
            page_tmp=(output_dir / sample_dataset.filename).with_suffix(".csv.page"),
            proc=MagicMock(),
            started=0.0,
        )

        slot.part.write_bytes(b"A" * 1000)
        slot.page_tmp.write_bytes(b"B" * 500)
        assert slot.current_size() == 1500

    def test_current_size_no_files(self, output_dir, sample_dataset):
        slot = _DownloadSlot(
            dataset=sample_dataset,
            target=output_dir / sample_dataset.filename,
            part=(output_dir / sample_dataset.filename).with_suffix(".csv.part"),
            page_tmp=(output_dir / sample_dataset.filename).with_suffix(".csv.page"),
            proc=MagicMock(),
            started=0.0,
        )
        assert slot.current_size() == 0
