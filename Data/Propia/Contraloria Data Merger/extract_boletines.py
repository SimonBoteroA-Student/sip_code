#!/usr/bin/env python3
"""
Extract tabular data from Boletín PDF files and save one merged, de-duplicated
CSV.

- Keeps the original column order:
  [Responsable Fiscal, tipo de documento, numero de documento, Entidad Afectada,
   TR, R, Ente que Reporta, Departamento, Municipio]
- Works on one PDF or a folder of PDFs; always produces a single merged CSV with
  duplicate rows removed (exact match across all columns).
- Relies on pdfplumber for line-based table detection (the sample PDF uses vector
  text plus ruling lines, not scanned images).
"""
import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

import pandas as pd  # type: ignore
import pdfplumber  # type: ignore

# Column order in the PDF (source)
COLS_SRC = [
    "Responsable Fiscal",
    "Tipo y Num Documento",
    "Entidad Afectada",
    "TR",
    "R",
    "Ente que Reporta",
    "Departamento",
    "Municipio",
]

# Desired output column order
COLS_OUT = [
    "Responsable Fiscal",
    "tipo de documento",
    "numero de documento",
    "Entidad Afectada",
    "TR",
    "R",
    "Ente que Reporta",
    "Departamento",
    "Municipio",
]

# Tuned to the provided Boletín layout (visible ruling lines, 8 columns)
TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "intersection_tolerance": 5,
    "snap_tolerance": 4,
    "join_tolerance": 3,
    "edge_min_length": 50,
    "min_words_vertical": 1,
    "min_words_horizontal": 1,
}


def clean_cell(val: str | None) -> str:
    if val is None:
        return ""
    # merge wrapped lines and strip stray control chars/spaces
    return " ".join(val.replace("\u00a0", " ").split()).strip()


def split_doc_field(value: str) -> tuple[str, str]:
    """
    Split combined document field into type (NIT/CC) and number.
    Returns empty strings when data is missing.
    """
    if not value:
        return "", ""
    match = re.match(r"\s*(NIT|CC)\s*(.*)$", value, flags=re.IGNORECASE)
    if match:
        doc_type = match.group(1).upper()
        number = match.group(2).strip()
    else:
        doc_type = ""
        number = value.strip()
    return doc_type, number


def normalize_row(row: Sequence[str | None], cols: Sequence[str]) -> List[str]:
    cleaned = [clean_cell(x) for x in row]
    if len(cleaned) < len(cols):
        cleaned += [""] * (len(cols) - len(cleaned))
    elif len(cleaned) > len(cols):
        cleaned = cleaned[: len(cols)]
    return cleaned


def extract_tables(pdf_path: Path) -> Iterable[List[str]]:
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.find_tables(table_settings=TABLE_SETTINGS)
            for table in tables:
                rows = table.extract()
                if not rows:
                    continue
                # Skip header rows that contain the column names
                for row in rows:
                    norm = normalize_row(row, COLS_SRC)
                    if any(h.lower() in norm[0].lower() for h in ("responsable fiscal",)):
                        continue
                    yield norm


def collect_pdfs(input_path: Path) -> List[Path]:
    if input_path.is_dir():
        return sorted(p for p in input_path.glob("**/*.pdf"))
    if input_path.suffix.lower() == ".pdf":
        return [input_path]
    raise SystemExit(f"Input must be a PDF file or folder, got: {input_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Boletín tables to one merged, de-duplicated CSV"
    )
    parser.add_argument("input", type=Path, help="PDF file or directory containing PDFs")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("boletines.csv"),
        help="Output CSV path (merged). Default: boletines.csv",
    )
    args = parser.parse_args()

    pdfs = collect_pdfs(args.input)
    if not pdfs:
        raise SystemExit("No PDF files found to process")

    all_rows: list[list[str]] = []
    for pdf in pdfs:
        rows = list(extract_tables(pdf))
        all_rows.extend(rows)
        print(f"Processed {pdf.name}: {len(rows)} rows")

    if not all_rows:
        raise SystemExit("No table rows found in provided PDFs.")

    df = pd.DataFrame(all_rows, columns=COLS_SRC)

    # Split combined document column into type/number and reorder
    doc_parts = df["Tipo y Num Documento"].map(split_doc_field)
    df["tipo de documento"], df["numero de documento"] = zip(*doc_parts)
    df = df.drop(columns=["Tipo y Num Documento"])
    df = df[COLS_OUT]

    before = len(df)
    df = df.drop_duplicates(keep="first", ignore_index=True)
    removed = before - len(df)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    dedup_msg = f", removed {removed} duplicate rows" if removed else ""
    print(f"✔ Wrote merged CSV to {args.output} ({len(df)} rows{dedup_msg})")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
