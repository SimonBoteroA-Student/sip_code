"""Tests for sip_engine data loaders and schema utilities.

Structure:
- TestCleanCurrency: unit tests for clean_currency() — always pass
- TestValidateColumns: unit tests for validate_columns() — always pass
- TestLoadContratos: integration tests for load_contratos()
- TestLoadPacoSiri: integration tests for load_paco_siri()
- TestEncodingReplace: encoding_errors='replace' tests
- TestFileNotFound: FileNotFoundError behaviour
- TestChunkedMemorySafety: chunked reading validates DATA-06
- TestImportable: verifies all 14 loaders are importable and callable

DATA-06: chunked read yields DataFrames without crash
DATA-07: dtypes match schema, currency cols cleaned to float
DATA-10: encoding errors replaced with replacement char, not crash
"""

from __future__ import annotations

import pytest
import pandas as pd

from sip_engine.data.schemas import clean_currency, validate_columns


# ============================================================
# Schema tests — always pass
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
# Loader tests — loaders.py implemented in Plan 02
# ============================================================

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

    def test_encoding_replace_produces_replacement_char(self, bad_byte_csv, monkeypatch):
        """DATA-10: encoding_errors='replace' yields U+FFFD, not crash or silent loss."""
        monkeypatch.setenv("SIP_SECOP_DIR", str(bad_byte_csv.parent))
        from sip_engine.data.loaders import load_contratos  # noqa: PLC0415
        chunks = list(load_contratos())
        assert len(chunks) >= 1
        all_text = " ".join(str(v) for chunk in chunks for v in chunk.values.flatten())
        assert "\ufffd" in all_text


# ============================================================
# Edge-case tests: FileNotFoundError, chunked memory safety, importability
# ============================================================

class TestFileNotFound:
    """FileNotFoundError raised with clear message when source file is missing."""

    def test_file_not_found(self, tmp_path, monkeypatch):
        """load_contratos() raises FileNotFoundError when SIP_SECOP_DIR has no CSV."""
        # Point to an empty temp dir — no contratos_SECOP.csv present
        monkeypatch.setenv("SIP_SECOP_DIR", str(tmp_path))
        from sip_engine.data.loaders import load_contratos  # noqa: PLC0415
        with pytest.raises(FileNotFoundError, match="contratos"):
            # Must call next() to trigger the generator
            next(load_contratos())


class TestChunkedMemorySafety:
    """DATA-06: chunked reads yield multiple smaller DataFrames, not one huge one."""

    def test_chunked_memory_safety(self, tmp_path, monkeypatch):
        """With chunk_size=2 and 5 data rows, load_contratos yields 3 chunks."""
        from sip_engine.data.schemas import CONTRATOS_USECOLS

        # Build a tiny CSV with exactly 5 data rows
        header = ",".join(CONTRATOS_USECOLS) + "\n"
        row_template = (
            "CO1.{i},CON-{i},REF-{i},Liquidado,Servicios,"
            "Contratación Directa,N/A,NIT,90000000{i},EMPRESA {i},"
            "Recursos Propios,$1,000,ENTIDAD TEST,899000001,Bogotá,Bogotá,"
            "Servicio test,2023-01-01,2023-01-05,2023-12-31\n"
        )
        content = header + "".join(row_template.format(i=i) for i in range(5))
        csv_path = tmp_path / "contratos_SECOP.csv"
        csv_path.write_text(content, encoding="utf-8")

        # Override chunk_size via SIP_* env — use monkeypatch on settings directly
        monkeypatch.setenv("SIP_SECOP_DIR", str(tmp_path))

        # We need to patch the settings singleton's chunk_size for this test
        from sip_engine.config import get_settings
        from unittest.mock import patch

        settings = get_settings()
        with patch.object(type(settings), "chunk_size", new=2):
            from sip_engine.data.loaders import load_contratos  # noqa: PLC0415
            # Reload settings fresh for this call via a new Settings instance
            from sip_engine.config.settings import Settings
            fresh_settings = Settings()
            fresh_settings.chunk_size = 2

            with patch("sip_engine.data.loaders.get_settings", return_value=fresh_settings):
                chunks = list(load_contratos())

        # 5 rows / chunk_size=2 → 3 chunks (2, 2, 1)
        assert len(chunks) == 3
        assert len(chunks[0]) == 2
        assert len(chunks[1]) == 2
        assert len(chunks[2]) == 1
        for chunk in chunks:
            assert isinstance(chunk, pd.DataFrame)


class TestAllLoadersImportable:
    """All 14 loader functions are importable and callable (return generators)."""

    def test_all_paco_loaders_importable(self):
        """All 5 PACO loader functions are importable and callable."""
        from sip_engine.data.loaders import (  # noqa: PLC0415
            load_paco_colusiones,
            load_paco_multas,
            load_paco_resp_fiscales,
            load_paco_sanciones_penales,
            load_paco_siri,
        )
        for fn in [
            load_paco_siri,
            load_paco_multas,
            load_paco_resp_fiscales,
            load_paco_colusiones,
            load_paco_sanciones_penales,
        ]:
            assert callable(fn), f"{fn.__name__} is not callable"

    def test_all_secop_loaders_importable(self):
        """All 9 SECOP loader functions are importable and callable."""
        from sip_engine.data.loaders import (  # noqa: PLC0415
            load_adiciones,
            load_boletines,
            load_contratos,
            load_ejecucion,
            load_ofertas,
            load_procesos,
            load_proponentes,
            load_proveedores,
            load_suspensiones,
        )
        for fn in [
            load_contratos,
            load_procesos,
            load_ofertas,
            load_proponentes,
            load_proveedores,
            load_boletines,
            load_ejecucion,
            load_suspensiones,
            load_adiciones,
        ]:
            assert callable(fn), f"{fn.__name__} is not callable"
