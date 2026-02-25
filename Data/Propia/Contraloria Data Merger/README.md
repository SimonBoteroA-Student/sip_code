# Boletines (PDF) → CSV

This folder contains extractors to convert Contraloría “Boletín de Responsables Fiscales” PDFs into **one merged CSV**, de-duplicated across all PDFs.

## Setup (recommended)

From the repo root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r "Data/Propia/Contraloria Data Merger/requirements.txt"
```

## Fast extraction (text/regex)

This is the recommended extractor for large batches of PDFs.

```bash
.venv/bin/python "Data/Propia/Contraloria Data Merger/extract_boletines_text.py" \
  "Data/Propia/Boletines" \
  -o "Data/Propia/boletines_from_pdfs.csv"
```

## Table-based extraction (slower)

If you need the line-detected table approach:

```bash
.venv/bin/python "Data/Propia/Contraloria Data Merger/extract_boletines.py" \
  "Data/Propia/Boletines" \
  -o "Data/Propia/boletines_from_pdfs.csv"
```

