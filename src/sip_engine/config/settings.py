"""Centralized configuration for sip_engine.

All file paths, encodings, and processing constants live here.
No hardcoded local paths should appear in business logic — use Settings instead.

Environment variable overrides (set before importing to take effect):
  SIP_PROJECT_ROOT   — override project root directory
  SIP_SECOP_DIR      — override SECOP CSV directory
  SIP_PACO_DIR       — override PACO CSV directory
  SIP_ARTIFACTS_DIR  — override artifacts output directory
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass, field
from pathlib import Path


def _project_root() -> Path:
    """Resolve project root from this file's location.

    Layout: settings.py → config/ → sip_engine/ → src/ → PROJECT_ROOT
    Using Path(__file__).resolve() ensures correct resolution from any CWD.

    SIP_PROJECT_ROOT env var overrides the file-based resolution.
    """
    env_override = os.environ.get("SIP_PROJECT_ROOT")
    if env_override:
        return Path(env_override)
    # __file__ is .../src/sip_engine/config/settings.py
    # .parent       → .../src/sip_engine/config/
    # .parent.parent → .../src/sip_engine/
    # .parent.parent.parent → .../src/
    # .parent.parent.parent.parent → PROJECT_ROOT
    return Path(__file__).resolve().parent.parent.parent.parent


@dataclass
class Settings:
    """Single source of truth for all sip_engine configuration.

    Instantiate once (or use get_settings() for the shared singleton).
    All paths are absolute and derived from project_root so the project
    can be run from any working directory.
    """

    # ------------------------------------------------------------------ #
    # Top-level directories (resolved in __post_init__)                   #
    # ------------------------------------------------------------------ #
    project_root: Path = field(default_factory=_project_root)
    secop_dir: Path = field(default=None)   # type: ignore[assignment]
    paco_dir: Path = field(default=None)    # type: ignore[assignment]
    artifacts_dir: Path = field(default=None)  # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # Artifact subdirectories (derived in __post_init__)                  #
    # ------------------------------------------------------------------ #
    artifacts_models_dir: Path = field(default=None)      # type: ignore[assignment]
    artifacts_evaluation_dir: Path = field(default=None)  # type: ignore[assignment]
    artifacts_rcac_dir: Path = field(default=None)        # type: ignore[assignment]
    artifacts_features_dir: Path = field(default=None)    # type: ignore[assignment]
    artifacts_iric_dir: Path = field(default=None)        # type: ignore[assignment]
    artifacts_labels_dir: Path = field(default=None)      # type: ignore[assignment]
    artifacts_shap_dir: Path = field(default=None)        # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # SECOP CSV paths (9 files, derived in __post_init__)                 #
    # ------------------------------------------------------------------ #
    contratos_path: Path = field(default=None)       # type: ignore[assignment]
    procesos_path: Path = field(default=None)        # type: ignore[assignment]
    ofertas_path: Path = field(default=None)         # type: ignore[assignment]
    proponentes_path: Path = field(default=None)     # type: ignore[assignment]
    proveedores_path: Path = field(default=None)     # type: ignore[assignment]
    ejecucion_path: Path = field(default=None)       # type: ignore[assignment]
    adiciones_path: Path = field(default=None)       # type: ignore[assignment]
    suspensiones_path: Path = field(default=None)    # type: ignore[assignment]
    boletines_path: Path = field(default=None)       # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # PACO CSV paths (5 files, derived in __post_init__)                  #
    # ------------------------------------------------------------------ #
    siri_path: Path = field(default=None)                      # type: ignore[assignment]
    responsabilidades_fiscales_path: Path = field(default=None)  # type: ignore[assignment]
    multas_secop_path: Path = field(default=None)              # type: ignore[assignment]
    colusiones_sic_path: Path = field(default=None)            # type: ignore[assignment]
    sanciones_penales_path: Path = field(default=None)         # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # Other data paths (derived in __post_init__)                         #
    # ------------------------------------------------------------------ #
    organized_people_path: Path = field(default=None)  # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # Config file paths (relative to this settings.py file)              #
    # ------------------------------------------------------------------ #
    model_weights_path: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent / "model_weights.json"
    )

    # ------------------------------------------------------------------ #
    # Artifact file paths (derived in __post_init__)                      #
    # ------------------------------------------------------------------ #
    iric_thresholds_path: Path = field(default=None)   # type: ignore[assignment]
    iric_scores_path: Path = field(default=None)        # type: ignore[assignment]
    feature_registry_path: Path = field(default=None)  # type: ignore[assignment]
    rcac_path: Path = field(default=None)               # type: ignore[assignment]
    rcac_bad_rows_path: Path = field(default=None)      # type: ignore[assignment]
    labels_path: Path = field(default=None)             # type: ignore[assignment]
    provider_history_index_path: Path = field(default=None)  # type: ignore[assignment]
    encoding_mappings_path: Path = field(default=None)       # type: ignore[assignment]
    features_path: Path = field(default=None)                # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # Encoding constants                                                  #
    # ------------------------------------------------------------------ #
    secop_encoding: str = "utf-8"
    paco_encoding: str = "utf-8"  # All PACO files are UTF-8 (verified empirically, DATA-10)

    # ------------------------------------------------------------------ #
    # Processing constants                                                #
    # ------------------------------------------------------------------ #
    chunk_size: int = 50_000

    # ------------------------------------------------------------------ #

    def __post_init__(self) -> None:
        """Resolve all derived paths, applying SIP_* env var overrides."""

        # ---- Apply env var overrides for top-level directories ----
        if env_val := os.environ.get("SIP_PROJECT_ROOT"):
            self.project_root = Path(env_val)
        if env_val := os.environ.get("SIP_SECOP_DIR"):
            self.secop_dir = Path(env_val)
        if env_val := os.environ.get("SIP_PACO_DIR"):
            self.paco_dir = Path(env_val)
        if env_val := os.environ.get("SIP_ARTIFACTS_DIR"):
            self.artifacts_dir = Path(env_val)

        # ---- Set defaults for directories that weren't overridden ----
        if self.secop_dir is None:
            self.secop_dir = self.project_root / "secopDatabases"
        if self.paco_dir is None:
            self.paco_dir = self.project_root / "Data" / "Propia" / "PACO"
        if self.artifacts_dir is None:
            self.artifacts_dir = self.project_root / "artifacts"

        # ---- Derive artifact subdirectories ----
        self.artifacts_models_dir = self.artifacts_dir / "models"
        self.artifacts_evaluation_dir = self.artifacts_dir / "evaluation"
        self.artifacts_rcac_dir = self.artifacts_dir / "rcac"
        self.artifacts_features_dir = self.artifacts_dir / "features"
        self.artifacts_iric_dir = self.artifacts_dir / "iric"
        self.artifacts_labels_dir = self.artifacts_dir / "labels"
        self.artifacts_shap_dir = self.artifacts_dir / "shap"

        # ---- Derive SECOP CSV paths ----
        self.contratos_path = self.secop_dir / "contratos_SECOP.csv"
        self.procesos_path = self.secop_dir / "procesos_SECOP.csv"
        self.ofertas_path = self.secop_dir / "ofertas_proceso_SECOP.csv"
        self.proponentes_path = self.secop_dir / "proponentes_proceso_SECOP.csv"
        self.proveedores_path = self.secop_dir / "proveedores_registrados.csv"
        self.ejecucion_path = self.secop_dir / "ejecucion_contratos.csv"
        self.adiciones_path = self.secop_dir / "adiciones.csv"
        self.suspensiones_path = self.secop_dir / "suspensiones_contratos.csv"
        self.rues_path = self.secop_dir / "rues_personas.csv"
        self.boletines_path = self.secop_dir / "boletines.csv"

        # ---- Derive PACO CSV paths ----
        self.siri_path = self.paco_dir / "sanciones_SIRI_PACO.csv"
        self.responsabilidades_fiscales_path = (
            self.paco_dir / "responsabilidades_fiscales_PACO.csv"
        )
        self.multas_secop_path = self.paco_dir / "multas_SECOP_PACO.csv"
        self.colusiones_sic_path = self.paco_dir / "colusiones_en_contratacion_SIC.csv"
        self.sanciones_penales_path = self.paco_dir / "sanciones_penales_FGN.csv"

        # ---- Derive other data paths ----
        self.organized_people_path = (
            self.project_root / "Data" / "organized_people_data.csv"
        )

        # ---- Derive artifact file paths ----
        self.iric_thresholds_path = self.artifacts_iric_dir / "iric_thresholds.json"
        self.iric_scores_path = self.artifacts_iric_dir / "iric_scores.parquet"
        self.feature_registry_path = (
            self.artifacts_features_dir / "feature_registry.json"
        )
        self.rcac_path = self.artifacts_rcac_dir / "rcac.pkl"
        self.rcac_bad_rows_path = self.artifacts_rcac_dir / "rcac_bad_rows.csv"
        self.labels_path = self.artifacts_labels_dir / "labels.parquet"
        self.provider_history_index_path = (
            self.artifacts_features_dir / "provider_history_index.pkl"
        )
        self.encoding_mappings_path = self.artifacts_features_dir / "encoding_mappings.json"
        self.features_path = self.artifacts_features_dir / "features.parquet"


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the shared Settings singleton.

    The result is cached — env var overrides must be set before the first
    call to take effect (or call Settings() directly for an uncached instance).
    """
    return Settings()
