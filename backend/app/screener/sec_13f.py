"""Descarga y parsea 13F-HR de las top instituciones desde SEC EDGAR.

Flujo por institución:
1. Búsqueda de CIK en EDGAR EFTS por nombre de institución
2. Submissions JSON → accession number del 13F-HR más reciente
3. Filing index → URL del XML de posiciones (informationTable)
4. Parse XML → lista de holdings {name, cusip, shares, value_usd_k}

Los resultados se almacenan en institutional_holdings por la job
update_institutional.py. Este módulo solo hace la descarga/parseo.
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, timedelta

import requests

logger = logging.getLogger("sec_13f")

_EDGAR_BASE = "https://data.sec.gov"
_EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
_EFTS_BASE = "https://efts.sec.gov/LATEST/search-index"
_HEADERS = {"User-Agent": "invest-feed-mvp escanillaalberto@gmail.com"}
_REQUEST_DELAY = 0.15  # segundos entre peticiones (límite SEC: 10 req/s)

# Top 30 instituciones por AUM — nombres tal como aparecen en EDGAR
TOP_INSTITUTION_NAMES: list[str] = [
    "Vanguard Group",
    "BlackRock",
    "FMR LLC",
    "State Street",
    "Wellington Management",
    "T Rowe Price",
    "JPMorgan Investment Management",
    "Capital Research",
    "Geode Capital Management",
    "Northern Trust",
    "Invesco",
    "Goldman Sachs",
    "Morgan Stanley Investment",
    "Dimensional Fund Advisors",
    "Schwab Asset Management",
    "American Century",
    "MFS Investment Management",
    "Dodge Cox",
    "Franklin Templeton",
    "Neuberger Berman",
    "Alliance Bernstein",
    "Nuveen",
    "Cohen Steers",
    "Lord Abbett",
    "Columbia Threadneedle",
    "Principal Asset Management",
    "Jennison Associates",
    "Putnam Investment",
    "Baird Advisors",
    "Calvert Research",
]

# Overrides directos de CIK para instituciones cuyo nombre de marca no hace fuzzy-match
# con el filer real en EDGAR -- muchas ya no presentan 13F-HR propio (solo 13F-NT,
# un "aviso" que delega en el filer combinado de la matriz tras una fusión/adquisición)
# y sus holdings quedan consolidados bajo otra entidad. Verificado manualmente contra
# submissions/CIK*.json (name + 13F-HR con reportDate reciente) en 2026-07.
KNOWN_CIK_OVERRIDES: dict[str, str] = {
    "T Rowe Price": "0000080255",
    "JPMorgan Investment Management": "0000019617",  # combinado bajo JPMorgan Chase & Co
    "Capital Research": "0001422849",  # Capital World Investors (una de varias divisiones de Capital Group)
    "Schwab Asset Management": "0000884546",
    "MFS Investment Management": "0000912938",
    "Franklin Templeton": "0000038777",
    "Alliance Bernstein": "0001109448",
    "Columbia Threadneedle": "0000820027",  # combinado bajo Ameriprise Financial, Inc
    "Principal Asset Management": "0001126328",  # combinado bajo Principal Financial Group Inc
    "Putnam Investment": "0000038777",  # combinado bajo Franklin Resources Inc (adquisición 2024) -- mismo CIK que Franklin Templeton
    "Baird Advisors": "0001648711",  # Baird Financial Group, Inc.
    "Calvert Research": "0000895421",  # combinado bajo Morgan Stanley (adquisición 2021)
}

# Instituciones cuyas holdings quedan repartidas entre VARIAS entidades legales,
# cada una presentando su propio 13F-HR, sin un filer combinado único (a
# diferencia de KNOWN_CIK_OVERRIDES). Vanguard Group Inc (CIK 102909) presentó
# un 13F-NT en Q1 2026 delegando en estas 10 sub-entidades -- verificado que
# cada una tiene 13F-HR propio con holdings reales. Se suman sus posiciones y
# se guardan bajo el CIK canónico de Vanguard Group para mantener una sola fila
# por institución en institutional_holdings.
MULTI_CIK_OVERRIDES: dict[str, list[str]] = {
    "Vanguard Group": [
        "0000933478",  # Vanguard Fiduciary Trust Co
        "0001550100",  # Vanguard Investments Australia, Ltd.
        "0002100121",  # Vanguard Portfolio Management LLC
        "0002100119",  # Vanguard Capital Management LLC
        "0000217448",  # Vanguard Marketing Corporation
        "0001767306",  # Vanguard Personalized Indexing Management, LLC
        "0001680208",  # Vanguard Asset Management, Ltd
        "0001984256",  # Vanguard National Trust Co
        "0001811242",  # Vanguard Global Advisers, LLC
        "0000947529",  # Vanguard Advisers Inc
    ],
}

# Sufijos comunes a eliminar para normalización de nombre de empresa
_SUFFIX_RE = re.compile(
    r"\b(INCORPORATED|CORPORATION|COMPANY|LIMITED|LTD|INC|CORP|CO|PLC|LLC|LP|"
    r"TRUST|HOLDINGS|GROUP|CLASS\s+[A-C])\b",
    re.IGNORECASE,
)
_NON_ALPHA_RE = re.compile(r"[^A-Z0-9 ]")


@dataclass
class Holding:
    name_issuer: str  # nameOfIssuer del XML 13F
    cusip: str
    shares: int
    value_usd_k: int


def normalize_company_name(name: str) -> str:
    """Normaliza nombre de empresa para comparación fuzzy."""
    name = name.upper()
    name = _NON_ALPHA_RE.sub(" ", name)
    name = _SUFFIX_RE.sub(" ", name)
    return re.sub(r"\s+", " ", name).strip()


# ---------------------------------------------------------------------------
# Búsqueda de CIK en EDGAR
# ---------------------------------------------------------------------------

_CIK_LOOKUP_URL = "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"
_CIK_LOOKUP_LINE_RE = re.compile(r"^(.*):(\d{10}):$")

_cik_lookup_cache: dict[str, list[str]] | None = None


def _is_relevant_key(key: str, target_keys: list[str]) -> bool:
    """True si `key` (nombre normalizado de una entidad EDGAR cualquiera) puede
    corresponder a alguno de los nombres normalizados de TOP_INSTITUTION_NAMES,
    ya sea exacto o como prefijo en cualquier dirección (nombres renombrados)."""
    for target in target_keys:
        if key == target or key.startswith(target + " "):
            return True
        if len(target) > len(key) >= 4 and target.startswith(key + " "):
            return True
    return False


def _load_cik_lookup() -> dict[str, list[str]]:
    """Descarga y filtra el listado completo de entidades EDGAR (nombre -> CIKs),
    quedándose solo con las relevantes para TOP_INSTITUTION_NAMES.

    Es la fuente autoritativa de SEC para resolver nombre de institución -> CIK;
    a diferencia de la full text search (efts.sec.gov), que indexa el CONTENIDO
    de los filings (no el nombre del filer) y devuelve coincidencias falsas.
    El archivo pesa ~40MB y tiene >1M entidades — se descarga en streaming y se
    descarta todo lo irrelevante al vuelo para no materializar el listado
    completo en memoria (evita un pico de RAM que puede tumbar el proceso).
    """
    global _cik_lookup_cache
    if _cik_lookup_cache is not None:
        return _cik_lookup_cache

    target_keys = [normalize_company_name(n) for n in TOP_INSTITUTION_NAMES]
    lookup: dict[str, list[str]] = {}
    with requests.get(_CIK_LOOKUP_URL, headers=_HEADERS, timeout=60, stream=True) as r:
        r.raise_for_status()
        for raw_line in r.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            m = _CIK_LOOKUP_LINE_RE.match(raw_line)
            if not m:
                continue
            raw_name, cik = m.group(1), m.group(2)
            key = normalize_company_name(raw_name)
            if not key or not _is_relevant_key(key, target_keys):
                continue
            lookup.setdefault(key, []).append(cik)

    _cik_lookup_cache = lookup
    logger.info("Cargado cik-lookup-data.txt: %d nombres relevantes retenidos", len(lookup))
    return lookup


_MAX_CIK_CANDIDATES = 15  # límite de verificaciones HTTP por institución
_MAX_STALE_DAYS = 550  # ~2 trimestres de margen; más antiguo = filer inactivo


def search_institution_cik(institution_name: str) -> str | None:
    """Busca el CIK de una institución vía el listado bulk de entidades EDGAR
    (cik-lookup-data.txt), desambiguando por nombres duplicados/renombrados y
    verificando cuál de los CIKs candidatos tiene 13F-HR reciente (no un filer
    inactivo que dejó de operar bajo ese CIK hace años)."""
    if institution_name in KNOWN_CIK_OVERRIDES:
        return KNOWN_CIK_OVERRIDES[institution_name].lstrip("0") or KNOWN_CIK_OVERRIDES[institution_name]

    lookup = _load_cik_lookup()
    key = normalize_company_name(institution_name)

    candidates: list[str] = list(lookup.get(key, []))
    if not candidates and key:
        # Fallback: el nombre normalizado es prefijo (o viceversa) de otra entidad
        # registrada con más/menos palabras, p.ej. "T ROWE PRICE" vs "T ROWE PRICE
        # INVESTMENT MANAGEMENT" (renombrada) — evita usar un solo token genérico
        # como "T", que haría matchear con miles de entidades no relacionadas.
        for cand_key, ciks in lookup.items():
            if cand_key.startswith(key + " ") or (
                len(key) > len(cand_key) >= 4 and key.startswith(cand_key + " ")
            ):
                candidates.extend(ciks)

    if not candidates:
        logger.warning("No se encontró CIK para '%s' en cik-lookup-data.txt", institution_name)
        return None

    best_cik: str | None = None
    best_date: date | None = None
    for cik in candidates[:_MAX_CIK_CANDIDATES]:
        result = get_latest_13f_accession(cik)
        if result is None:
            continue
        _, report_date = result
        if best_date is None or report_date > best_date:
            best_cik, best_date = cik, report_date

    if best_cik is None or best_date is None:
        logger.warning(
            "'%s': %d CIK candidatos en EDGAR pero ninguno con 13F-HR", institution_name, len(candidates)
        )
        return None

    if (date.today() - best_date).days > _MAX_STALE_DAYS:
        logger.warning(
            "'%s': mejor candidato CIK %s tiene el último 13F-HR de %s (>%d días, filer inactivo)",
            institution_name, best_cik, best_date, _MAX_STALE_DAYS,
        )
        return None

    return best_cik.lstrip("0") or best_cik


# ---------------------------------------------------------------------------
# Recuperación de accession number del último 13F-HR
# ---------------------------------------------------------------------------

def get_latest_13f_accession(cik: str) -> tuple[str, date] | None:
    """Retorna (accession_number, report_date) del 13F-HR más reciente o None."""
    padded = cik.zfill(10)
    url = f"{_EDGAR_BASE}/submissions/CIK{padded}.json"
    try:
        time.sleep(_REQUEST_DELAY)
        r = requests.get(url, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.warning("Error obteniendo submissions para CIK %s: %s", cik, exc)
        return None

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    report_dates = recent.get("reportDate", [])

    for i, form in enumerate(forms):
        if form == "13F-HR" and i < len(accessions):
            acc = accessions[i]
            rd = report_dates[i] if i < len(report_dates) else ""
            try:
                return acc, date.fromisoformat(rd)
            except ValueError:
                return acc, date.today()

    # Buscar en filings históricos si los recientes no tienen 13F-HR
    for page_url in data.get("filings", {}).get("files", []):
        # Los archivos de filings históricos no se descargan aquí para mantener simple
        break

    logger.info("Sin 13F-HR en filings recientes para CIK %s", cik)
    return None


def get_13f_accession_for_quarter(cik: str, quarter: date) -> str | None:
    """Retorna el accession_number del 13F-HR cuyo reportDate coincide exactamente
    con `quarter`, o None si esa institución no tiene un filing para ese trimestre.

    A diferencia de get_latest_13f_accession (que siempre trae el más reciente),
    esto permite descargar un trimestre histórico concreto -- necesario para
    cargar el trimestre ANTERIOR y así poder calcular la tendencia de
    acumulación/distribución del criterio I (ver evaluate_i en canslim.py)."""
    padded = cik.zfill(10)
    url = f"{_EDGAR_BASE}/submissions/CIK{padded}.json"
    try:
        time.sleep(_REQUEST_DELAY)
        r = requests.get(url, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.warning("Error obteniendo submissions para CIK %s: %s", cik, exc)
        return None

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    report_dates = recent.get("reportDate", [])

    for i, form in enumerate(forms):
        if form != "13F-HR" or i >= len(accessions) or i >= len(report_dates):
            continue
        try:
            rd = date.fromisoformat(report_dates[i])
        except ValueError:
            continue
        if rd == quarter:
            return accessions[i]

    # El trimestre buscado puede quedar fuera de la ventana "recent" (~1000
    # filings más recientes) para filers muy antiguos -- se revisan los
    # archivos de filings históricos paginados si existen.
    for page in data.get("filings", {}).get("files", []):
        page_name = page.get("name")
        if not page_name:
            continue
        try:
            time.sleep(_REQUEST_DELAY)
            pr = requests.get(f"{_EDGAR_BASE}/submissions/{page_name}", headers=_HEADERS, timeout=20)
            pr.raise_for_status()
            page_data = pr.json()
        except Exception as exc:
            logger.warning("Error obteniendo página histórica %s para CIK %s: %s", page_name, cik, exc)
            continue
        forms_p = page_data.get("form", [])
        accessions_p = page_data.get("accessionNumber", [])
        report_dates_p = page_data.get("reportDate", [])
        for i, form in enumerate(forms_p):
            if form != "13F-HR" or i >= len(accessions_p) or i >= len(report_dates_p):
                continue
            try:
                rd = date.fromisoformat(report_dates_p[i])
            except ValueError:
                continue
            if rd == quarter:
                return accessions_p[i]

    logger.info("Sin 13F-HR con reportDate=%s para CIK %s", quarter, cik)
    return None


# ---------------------------------------------------------------------------
# Descarga y parseo del XML de holdings
# ---------------------------------------------------------------------------

def _get_xml_url_from_index(cik: str, accession: str) -> str | None:
    """Parsea el índice de filing para encontrar el XML de information table."""
    cik_int = str(int(cik))  # sin ceros a la izquierda
    acc_nodash = accession.replace("-", "")
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{accession}-index.htm"
    try:
        time.sleep(_REQUEST_DELAY)
        r = requests.get(index_url, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        html = r.text

        # Buscar todos los hrefs que apunten a XML dentro de este filing.
        # EDGAR duplica cada XML bajo una carpeta xslFormXXX/ que es en realidad
        # una vista renderizada en HTML (mismo nombre .xml, contenido HTML) —
        # se excluye para no parsear HTML como si fuera el XML crudo.
        xml_hrefs = [
            href
            for href in re.findall(r'href="(/Archives/edgar/data/[^"]+\.xml)"', html, re.IGNORECASE)
            if "/xslForm" not in href
        ]
        if not xml_hrefs:
            return None

        # Si hay solo uno, ese es
        if len(xml_hrefs) == 1:
            return f"https://www.sec.gov{xml_hrefs[0]}"

        # Si hay varios (típico: primary_doc.xml de portada + el XML real de
        # holdings), cada documento aparece en su propia fila <tr> de la tabla
        # "Document Format Files", con una columna Type que vale literalmente
        # "INFORMATION TABLE" para el XML de holdings (frente a "13F-HR" para
        # la portada) -- se busca el href dentro de esa fila en concreto, en vez
        # de una heurística de "texto más cercano" que es frágil: EDGAR repite
        # la etiqueta "INFORMATION TABLE" pegada a un href excluido (la copia
        # xslForm/) justo antes del href real, haciendo que la distancia de
        # texto favorezca por error al primary_doc.xml de portada.
        for row in re.findall(r"<tr[^>]*>.*?</tr>", html, re.IGNORECASE | re.DOTALL):
            if "information table" not in row.lower():
                continue
            for href in re.findall(r'href="(/Archives/edgar/data/[^"]+\.xml)"', row, re.IGNORECASE):
                if href in xml_hrefs:
                    return f"https://www.sec.gov{href}"

        return f"https://www.sec.gov{xml_hrefs[0]}"

    except Exception as exc:
        logger.warning("Error obteniendo índice de filing %s/%s: %s", cik, accession, exc)
        return None


def _parse_holdings_xml(xml_bytes: bytes) -> list[Holding]:
    """Parsea el XML de la information table de un 13F-HR."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.warning("Error parseando XML 13F: %s", exc)
        return []

    holdings: list[Holding] = []
    for info in root.findall(".//{*}infoTable"):
        name = (info.findtext("{*}nameOfIssuer") or info.findtext("nameOfIssuer") or "").strip()
        cusip = (info.findtext("{*}cusip") or info.findtext("cusip") or "").strip()
        value_text = (info.findtext("{*}value") or info.findtext("value") or "0").replace(",", "").strip()

        # ElementTree Elements son "falsy" si no tienen hijos (aunque no sean None) —
        # un `or` entre dos find() con un <sshPrnamt>1000</sshPrnamt> sin hijos
        # descartaría el match real y seguiría al segundo find() (sin namespace,
        # que no encuentra nada), dejando shares en 0 siempre.
        shr_amt = info.find(".//{*}sshPrnamt")
        if shr_amt is None:
            shr_amt = info.find(".//sshPrnamt")
        shr_type = info.find(".//{*}sshPrnamtType")
        if shr_type is None:
            shr_type = info.find(".//sshPrnamtType")

        shares = 0
        if shr_amt is not None and (shr_type is None or (shr_type.text or "").strip().upper() == "SH"):
            try:
                shares = int((shr_amt.text or "0").replace(",", "").strip())
            except ValueError:
                pass

        try:
            value_k = int(value_text or "0")
        except ValueError:
            value_k = 0

        if name and cusip and (shares > 0 or value_k > 0):
            holdings.append(Holding(name_issuer=name.upper(), cusip=cusip, shares=shares, value_usd_k=value_k))

    return holdings


def download_institution_holdings(
    cik: str, institution_name: str, target_quarter: date | None = None,
) -> tuple[list[Holding], date | None]:
    """Descarga y parsea las posiciones del 13F-HR de una institución.
    Si `target_quarter` es None, coge el más reciente disponible; si se indica,
    busca específicamente el filing de ese trimestre (necesario para cargar
    trimestres históricos, p.ej. el anterior, para la tendencia del criterio I).
    Retorna (holdings, report_date). Lista vacía si falla."""
    if target_quarter is not None:
        accession = get_13f_accession_for_quarter(cik, target_quarter)
        if accession is None:
            return [], None
        report_date = target_quarter
    else:
        result = get_latest_13f_accession(cik)
        if result is None:
            return [], None
        accession, report_date = result

    xml_url = _get_xml_url_from_index(cik, accession)
    if xml_url is None:
        logger.warning("%s (CIK %s): no se encontró XML en el índice del filing", institution_name, cik)
        return [], report_date

    try:
        time.sleep(_REQUEST_DELAY)
        r = requests.get(xml_url, headers=_HEADERS, timeout=60)
        r.raise_for_status()
        holdings = _parse_holdings_xml(r.content)
        logger.info("%s: %d posiciones parseadas (quarter %s)", institution_name, len(holdings), report_date)
        return holdings, report_date
    except Exception as exc:
        logger.warning("%s: error descargando XML %s: %s", institution_name, xml_url, exc)
        return [], report_date


# ---------------------------------------------------------------------------
# Helpers de quarter
# ---------------------------------------------------------------------------

def quarter_end_date(d: date) -> date:
    """Retorna el último día del trimestre de la fecha dada."""
    if d.month <= 3:
        return date(d.year, 3, 31)
    elif d.month <= 6:
        return date(d.year, 6, 30)
    elif d.month <= 9:
        return date(d.year, 9, 30)
    else:
        return date(d.year, 12, 31)


def prior_quarter_end(q: date) -> date:
    """Retorna el último día del trimestre anterior al trimestre q."""
    if q.month == 3:    # Q1 ends Mar 31 → prior is Q4 prev year
        return date(q.year - 1, 12, 31)
    elif q.month == 6:  # Q2 ends Jun 30 → prior is Q1
        return date(q.year, 3, 31)
    elif q.month == 9:  # Q3 ends Sep 30 → prior is Q2
        return date(q.year, 6, 30)
    else:               # Q4 ends Dec 31 → prior is Q3
        return date(q.year, 9, 30)


def latest_available_quarter() -> date:
    """Último trimestre cuyos 13F ya habrán sido publicados (deadline: 45 días tras fin de trimestre)."""
    today = date.today()
    candidates = []
    for year in [today.year - 1, today.year]:
        for month_end in [3, 6, 9, 12]:
            day = 30 if month_end in (6, 9) else (31 if month_end in (3, 12) else 28)
            q = date(year, month_end, day)
            deadline = q + timedelta(days=45)
            if today >= deadline:
                candidates.append(q)
    return max(candidates) if candidates else date(today.year - 1, 12, 31)
