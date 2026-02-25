#!/usr/bin/env python3
"""
Fast Boletín de Responsables Fiscales PDF → merged CSV extractor.

This variant uses page text extraction + regex heuristics (much faster than
table line-detection) and produces a single, de-duplicated CSV across ALL PDFs
in the input folder.

Output columns (in order):
  Responsable Fiscal, tipo de documento, numero de documento, Entidad Afectada,
  TR, R, Ente que Reporta, Departamento, Municipio
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable

import pandas as pd  # type: ignore
import pdfplumber  # type: ignore


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

# Department names as they commonly appear in the PDFs (uppercase).
# Used to reliably split "Ente que Reporta" vs "Departamento" vs "Municipio".
DEPARTAMENTOS = [
    "AMAZONAS",
    "ANTIOQUIA",
    "ARAUCA",
    "ATLANTICO",
    "BOGOTA, D.C.",
    "BOLIVAR",
    "BOYACA",
    "CALDAS",
    "CAQUETA",
    "CASANARE",
    "CAUCA",
    "CESAR",
    "CHOCO",
    "CORDOBA",
    "CUNDINAMARCA",
    "GUAINIA",
    "GUAJIRA",
    "GUAVIARE",
    "HUILA",
    "MAGDALENA",
    "META",
    "NARIÑO",
    "NORTE SANTANDER",
    "PUTUMAYO",
    "QUINDIO",
    "RISARALDA",
    "SAN ANDRES",
    "SANTANDER",
    "SUCRE",
    "TOLIMA",
    "VALLE DEL CAUCA",
    "VAUPES",
    "VICHADA",
]


DOC_RE = re.compile(r"\b(?P<doc_type>CC|NIT)\b\s*(?P<doc_num>[\d\.\-]+)\b", re.I)
TRR_RE = re.compile(r"\b(?P<tr>[IS])\s+(?P<r>\d+)\b")
PAGE_NO_RE = re.compile(r"--\s*\d+\s+of\s+\d+\s*--", re.I)


def strip_accents(s: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)
    )


def clean_ws(s: str) -> str:
    return " ".join(s.replace("\u00a0", " ").split()).strip()


def is_noise_line(line: str) -> bool:
    l = clean_ws(line)
    if not l:
        return True
    if l.startswith("Boletín de Responsables Fiscales"):
        return True
    if l.startswith("CONTRALORIA DELEGADA"):
        return True
    if l.startswith("Responsable Fiscal Tipo y Num"):
        return True
    if "SIBOR TR=" in l:
        return True
    if PAGE_NO_RE.search(l):
        return True
    # Common footer initials (varies by bulletin)
    if l in {"JMMC"}:
        return True
    # Date line like: "viernes 01 de julio de 2022"
    if re.match(
        r"^(lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\s+\d{2}\s+de\s+",
        l,
        flags=re.I,
    ):
        return True
    return False


def collect_pdfs(input_path: Path) -> list[Path]:
    if input_path.is_dir():
        return sorted(p for p in input_path.glob("**/*.pdf"))
    if input_path.suffix.lower() == ".pdf":
        return [input_path]
    raise SystemExit(f"Input must be a PDF file or folder, got: {input_path}")


def record_looks_complete(text: str) -> bool:
    if not DOC_RE.search(text):
        return False
    if not TRR_RE.search(text):
        return False
    # Ensure at least one department is present somewhere (helps avoid premature splits).
    t = strip_accents(text.upper())
    return any(strip_accents(d.upper()) in t for d in DEPARTAMENTOS)


def split_after_trr(after: str) -> tuple[str, str, str]:
    """
    Split the trailing text into (ente_que_reporta, departamento, municipio).
    Uses the last department match so "Ente..." can contain department words.
    """
    if not after:
        return "", "", ""

    after_clean = clean_ws(after)
    after_key = strip_accents(after_clean.upper())

    best_span: tuple[int, int] | None = None
    best_dept: str | None = None

    for dept in DEPARTAMENTOS:
        dept_key = strip_accents(dept.upper())
        for m in re.finditer(rf"\b{re.escape(dept_key)}\b", after_key):
            span = m.span()
            if best_span is None or span[0] >= best_span[0]:
                best_span = span
                best_dept = dept

    if best_span is None or best_dept is None:
        return after_clean, "", ""

    dept_start, dept_end = best_span
    ente = clean_ws(after_clean[:dept_start])
    departamento = clean_ws(after_clean[dept_start:dept_end])
    municipio = clean_ws(after_clean[dept_end:])

    # Prefer the canonical dept label from our list (keeps accents/punctuation stable).
    departamento = best_dept
    return ente, departamento, municipio


def parse_record(record: str) -> dict[str, str] | None:
    rec = clean_ws(record)

    m_doc = DOC_RE.search(rec)
    if not m_doc:
        return None

    responsable = clean_ws(rec[: m_doc.start()])
    doc_type = m_doc.group("doc_type").upper()
    doc_num = clean_ws(m_doc.group("doc_num"))

    rest = clean_ws(rec[m_doc.end() :])
    m_trr = TRR_RE.search(rest)
    if not m_trr:
        return None

    entidad = clean_ws(rest[: m_trr.start()])
    tr = m_trr.group("tr").upper()
    r = m_trr.group("r")
    after = clean_ws(rest[m_trr.end() :])

    ente, departamento, municipio = split_after_trr(after)

    return {
        "Responsable Fiscal": responsable,
        "tipo de documento": doc_type,
        "numero de documento": doc_num,
        "Entidad Afectada": entidad,
        "TR": tr,
        "R": r,
        "Ente que Reporta": ente,
        "Departamento": departamento,
        "Municipio": municipio,
    }


def extract_records_from_pdf(pdf_path: Path) -> Iterable[dict[str, str]]:
    with pdfplumber.open(pdf_path) as pdf:
        carry: list[str] = []

        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [clean_ws(l) for l in text.splitlines() if not is_noise_line(l)]
            if not lines:
                continue

            for line in lines:
                carry.append(line)
                candidate = clean_ws(" ".join(carry))
                if record_looks_complete(candidate):
                    parsed = parse_record(candidate)
                    if parsed:
                        yield parsed
                        carry = []

        # drop incomplete tail (usually headers/footers)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fast Boletín PDF → one merged, de-duplicated CSV (text/regex mode)"
    )
    parser.add_argument("input", type=Path, help="PDF file or directory containing PDFs")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("boletines.csv"),
        help="Output CSV path. Default: boletines.csv",
    )
    args = parser.parse_args()

    pdfs = collect_pdfs(args.input)
    if not pdfs:
        raise SystemExit("No PDF files found to process")

    rows: list[dict[str, str]] = []
    for pdf in pdfs:
        extracted = list(extract_records_from_pdf(pdf))
        rows.extend(extracted)
        print(f"Processed {pdf.name}: {len(extracted)} rows", flush=True)

    if not rows:
        raise SystemExit("No records parsed from provided PDFs.")

    df = pd.DataFrame(rows, columns=COLS_OUT)

    # Normalize whitespace for de-duplication while keeping original columns.
    for col in COLS_OUT:
        df[col] = df[col].astype(str).map(clean_ws)

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

