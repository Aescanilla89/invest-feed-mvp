from fastapi import APIRouter

from app.models.schemas import DataLimitation, DataLimitationsSchema

router = APIRouter(prefix="/meta", tags=["meta"])

_CRITERIA_LIMITATIONS = [
    DataLimitation(criterion="C", verifiable=True, reason="Crecimiento EPS trimestral YoY vía yfinance"),
    DataLimitation(criterion="A", verifiable=True, reason="Crecimiento EPS anual vía yfinance"),
    DataLimitation(
        criterion="N",
        verifiable=True,
        reason="Solo la parte de máximo de 52 semanas con volumen. No evalúa 'nuevo producto/gestión'.",
    ),
    DataLimitation(
        criterion="S",
        verifiable=True,
        reason="Tendencia de shares outstanding vía SEC EDGAR (companyfacts), no vía yfinance.",
    ),
    DataLimitation(criterion="L", verifiable=True, reason="Fuerza relativa frente a SPY como benchmark"),
    DataLimitation(
        criterion="I",
        verifiable=False,
        reason="Requiere agregar Form 13F de todos los filers (dataset bulk trimestral de SEC). "
        "No disponible como endpoint por ticker en este MVP. Planificado para fase 2.",
    ),
    DataLimitation(criterion="M", verifiable=True, reason="Stage de Weinstein calculado sobre SPY como proxy del mercado"),
]

_SOURCE_NOTES = [
    "yfinance no es una API oficial (scraping de Yahoo Finance): sin SLA, puede romperse sin aviso.",
    "Rate limit de yfinance no documentado oficialmente; el job aplica pausas entre tickers.",
    "Cobertura de datos fundamentales de yfinance es inconsistente fuera de empresas large-cap.",
    "SEC EDGAR (data.sec.gov) es la fuente oficial usada para shares outstanding (criterio S); "
    "gratis y sin API key, pero los filings tienen delay de varias semanas tras cierre de trimestre.",
    "Ningún dato de este feed tiene fines de ejecución de órdenes ni asesoramiento financiero: "
    "es información educativa, con retraso (no apto para intradía).",
]


@router.get("/data-limitations", response_model=DataLimitationsSchema)
def get_data_limitations() -> DataLimitationsSchema:
    return DataLimitationsSchema(source_notes=_SOURCE_NOTES, canslim_criteria=_CRITERIA_LIMITATIONS)
