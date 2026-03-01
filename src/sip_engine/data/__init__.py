"""Data loading and processing module for sip_engine."""

from sip_engine.data.loaders import (
    load_adiciones,
    load_boletines,
    load_contratos,
    load_ejecucion,
    load_ofertas,
    load_paco_colusiones,
    load_paco_multas,
    load_paco_resp_fiscales,
    load_paco_sanciones_penales,
    load_paco_siri,
    load_procesos,
    load_proponentes,
    load_proveedores,
    load_suspensiones,
)

__all__ = [
    "load_contratos",
    "load_procesos",
    "load_ofertas",
    "load_proponentes",
    "load_proveedores",
    "load_boletines",
    "load_ejecucion",
    "load_suspensiones",
    "load_adiciones",
    "load_paco_siri",
    "load_paco_multas",
    "load_paco_resp_fiscales",
    "load_paco_colusiones",
    "load_paco_sanciones_penales",
]
