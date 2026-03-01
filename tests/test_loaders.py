"""Tests for sip_engine data loaders and schema utilities.

Structure:
- TestCleanCurrency: unit tests for clean_currency() — pass NOW (schemas.py exists)
- TestValidateColumns: unit tests for validate_columns() — pass NOW
- TestLoadContratos: integration stubs for load_contratos() — xfail until Plan 02
- TestLoadPacoSiri: integration stubs for load_paco_siri() — xfail until Plan 02
- TestEncodingReplace: integration stubs for encoding_errors='replace' — xfail until Plan 02

DATA-06: chunked read yields DataFrames without crash
DATA-07: dtypes match schema, currency cols cleaned to float
DATA-10: encoding errors replaced with replacement char, not crash
"""

from __future__ import annotations

import pytest
import pandas as pd

from sip_engine.data.schemas import clean_currency, validate_columns


# ============================================================
# Schema tests — pass NOW (schemas.py complete)
# ============================================================

class TestCleanCurrency:
    """Tests for clean_currency() — '$X,XXX' -> Float64 conversion."""

    def test_standard_format(self):
        """Standard SECOP currency format with dollar sign and thousands comma."""
        s = pd.Series(["$10,979,236,356", "$1,234"])
        result = clean_currency(s)
        assert list(result) == [10_979_236_356.0, 1_234.0]

    def test_nan_passthrough(self):
        """NaN/NA values in the series should remain NA after cleaning."""
        s = pd.Series(["$100", pd.NA, "$200"])
        result = clean_currency(s)
        assert pd.isna(result.iloc[1])
        assert result.iloc[0] == 100.0
        assert result.iloc[2] == 200.0

    def test_no_dollar_sign(self):
        """Values without dollar sign (only commas) should also clean correctly."""
        s = pd.Series(["1,234,567"])
        result = clean_currency(s)
        assert result.iloc[0] == 1_234_567.0

    def test_small_integer_value(self):
        """Small integer-like currency values."""
        s = pd.Series(["$450,000", "$75,800,000"])
        result = clean_currency(s)
        assert result.iloc[0] == 450_000.0
        assert result.iloc[1] == 75_800_000.0

    def test_returns_float64_dtype(self):
        """Result must use nullable Float64 (not float64) for NA support."""
        s = pd.Series(["$1,000"])
        result = clean_currency(s)
        assert str(result.dtype) == "Float64"

    def test_all_na_series(self):
        """All-NA series should return all-NA Float64 series."""
        s = pd.Series([pd.NA, pd.NA])
        result = clean_currency(s)
        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[1])


class TestValidateColumns:
    """Tests for validate_columns() — fail-fast header check."""

    def test_missing_column_raises(self, missing_column_csv):
        """ValueError raised when a required column is absent from the CSV header."""
        from sip_engine.data.schemas import CONTRATOS_USECOLS
        with pytest.raises(ValueError, match="Missing required columns"):
            validate_columns(str(missing_column_csv), CONTRATOS_USECOLS)

    def test_missing_column_message_names_column(self, missing_column_csv):
        """Error message should identify which column is missing."""
        from sip_engine.data.schemas import CONTRATOS_USECOLS
        with pytest.raises(ValueError) as exc_info:
            validate_columns(str(missing_column_csv), CONTRATOS_USECOLS)
        # The last column was dropped in the fixture — it should appear in the message
        assert CONTRATOS_USECOLS[-1] in str(exc_info.value)

    def test_headerless_skips_validation(self, tiny_siri_csv):
        """Integer usecols signals headerless file — validation is a no-op."""
        # Should not raise — integer list means positional (headerless) file
        validate_columns(str(tiny_siri_csv), [4, 5])

    def test_valid_columns_no_error(self, tiny_contratos_csv):
        """No error when all required columns are present."""
        from sip_engine.data.schemas import CONTRATOS_USECOLS
        # Should not raise
        validate_columns(str(tiny_contratos_csv), CONTRATOS_USECOLS)

    def test_empty_expected_list(self, tiny_contratos_csv):
        """Empty expected list should not raise (no requirements = always valid)."""
        validate_columns(str(tiny_contratos_csv), [])


# ============================================================
# Loader tests — xfail until Plan 02 creates loaders.py
# ============================================================

@pytest.mark.xfail(
    reason="loaders.py not yet created — will be implemented in Plan 02",
    raises=ImportError,
    strict=True,
)
class TestLoadContratos:
    """DATA-06 / DATA-07: Chunked contratos loader."""

    def test_yields_dataframes(self, tiny_contratos_csv, monkeypatch):
        """DATA-06: chunked read yields DataFrames without crash."""
        monkeypatch.setenv("SIP_SECOP_DIR", str(tiny_contratos_csv.parent))
        from sip_engine.data.loaders import load_contratos  # noqa: PLC0415
        chunks = list(load_contratos())
        assert len(chunks) >= 1
        assert isinstance(chunks[0], pd.DataFrame)

    def test_correct_dtypes(self, tiny_contratos_csv, monkeypatch):
        """DATA-07: dtypes match schema, document columns are string type."""
        monkeypatch.setenv("SIP_SECOP_DIR", str(tiny_contratos_csv.parent))
        from sip_engine.data.loaders import load_contratos  # noqa: PLC0415
        chunk = next(load_contratos())
        assert chunk["Documento Proveedor"].dtype == "string"

    def test_currency_cleaned_to_float(self, tiny_contratos_csv, monkeypatch):
        """DATA-07: currency columns are Float64 after cleaning, not str."""
        monkeypatch.setenv("SIP_SECOP_DIR", str(tiny_contratos_csv.parent))
        from sip_engine.data.loaders import load_contratos  # noqa: PLC0415
        chunk = next(load_contratos())
        assert str(chunk["Valor del Contrato"].dtype) == "Float64"

    def test_only_usecols_present(self, tiny_contratos_csv, monkeypatch):
        """DATA-07: only schema-defined columns are loaded (no extras)."""
        monkeypatch.setenv("SIP_SECOP_DIR", str(tiny_contratos_csv.parent))
        from sip_engine.data.schemas import CONTRATOS_USECOLS  # noqa: PLC0415
        from sip_engine.data.loaders import load_contratos  # noqa: PLC0415
        chunk = next(load_contratos())
        # Currency cols are cleaned and retained — rest of usecols should be present
        for col in CONTRATOS_USECOLS:
            assert col in chunk.columns, f"Missing expected column: {col}"


@pytest.mark.xfail(
    reason="loaders.py not yet created — will be implemented in Plan 02",
    raises=ImportError,
    strict=True,
)
class TestLoadPacoSiri:
    """DATA-04: Headerless positional read for SIRI sanctions file."""

    def test_headerless_read(self, tiny_siri_csv, monkeypatch):
        """DATA-04: positional columns loaded and renamed correctly."""
        monkeypatch.setenv("SIP_PACO_DIR", str(tiny_siri_csv.parent))
        from sip_engine.data.loaders import load_paco_siri  # noqa: PLC0415
        chunk = next(load_paco_siri())
        assert "tipo_documento" in chunk.columns
        assert "numero_documento" in chunk.columns

    def test_colnames_assigned(self, tiny_siri_csv, monkeypatch):
        """Column names are SIRI_COLNAMES, not integer indices."""
        monkeypatch.setenv("SIP_PACO_DIR", str(tiny_siri_csv.parent))
        from sip_engine.data.loaders import load_paco_siri  # noqa: PLC0415
        chunk = next(load_paco_siri())
        # Should not have integer column names
        assert 4 not in chunk.columns
        assert 5 not in chunk.columns

    def test_spanish_chars_correct(self, tiny_siri_csv, monkeypatch):
        """UTF-8 encoding preserves Spanish characters correctly (not garbled Latin-1)."""
        monkeypatch.setenv("SIP_PACO_DIR", str(tiny_siri_csv.parent))
        from sip_engine.data.loaders import load_paco_siri  # noqa: PLC0415
        chunk = next(load_paco_siri())
        # First row has "CÉDULA DE CIUDADANÍA" — must NOT be garbled
        assert "CÉDULA DE CIUDADANÍA" in chunk["tipo_documento"].values


@pytest.mark.xfail(
    reason="loaders.py not yet created — will be implemented in Plan 02",
    raises=ImportError,
    strict=True,
)
class TestEncodingReplace:
    """DATA-10: encoding_errors='replace' — bad bytes become replacement char, not crash."""

    def test_bad_bytes_replaced(self, bad_byte_csv, monkeypatch):
        """DATA-10: file with invalid UTF-8 byte loads without UnicodeDecodeError."""
        monkeypatch.setenv("SIP_SECOP_DIR", str(bad_byte_csv.parent))
        from sip_engine.data.loaders import load_contratos  # noqa: PLC0415
        chunk = next(load_contratos())
        # Should contain at least one row (bad byte replaced, not crashed)
        assert len(chunk) >= 1

    def test_replacement_char_present(self, bad_byte_csv, monkeypatch):
        """Replacement character (U+FFFD) appears in place of the bad byte."""
        monkeypatch.setenv("SIP_SECOP_DIR", str(bad_byte_csv.parent))
        from sip_engine.data.loaders import load_contratos  # noqa: PLC0415
        chunk = next(load_contratos())
        # Flatten all string values and check for replacement char
        all_text = " ".join(str(v) for v in chunk.values.flatten())
        assert "\ufffd" in all_text, "Expected replacement char U+FFFD from bad byte"
