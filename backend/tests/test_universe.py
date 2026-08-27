"""Tests para universe.py — scraping de Russell 2000 y mercado europeo.

Los tests mockean requests.get para no hacer llamadas reales de red,
lo que los hace rápidos y deterministas.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.screener.universe import (
    UniverseScrapeError,
    _scrape_european_index,
    get_russell2000_tickers,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(text: str, status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


def _make_vanguard_payload(tickers: list[str], include_blank: bool = True) -> dict:
    """Construye una respuesta JSON de Vanguard VTWO sintética con la estructura real."""
    entities = [{"ticker": t, "longName": f"{t} Inc"} for t in tickers]
    if include_blank:
        entities.append({"ticker": "", "longName": "CASH"})
    return {
        "size": len(tickers),
        "asOfDate": "2026-07-31T00:00:00-04:00",
        "fund": {"entity": entities},
    }


def _mock_vanguard_response(tickers: list[str], include_blank: bool = True) -> MagicMock:
    payload = _make_vanguard_payload(tickers, include_blank=include_blank)
    return _mock_response("", json_data=payload)


def _make_wikipedia_html(ticker_col: str, tickers: list[str]) -> str:
    """Construye un HTML mínimo con una tabla Wikipedia de índice bursátil."""
    rows = "\n".join(f"<tr><td>Company {t}</td><td>{t}</td></tr>" for t in tickers)
    return f"""
    <html><body>
    <table class="wikitable">
      <tr><th>Company</th><th>{ticker_col}</th></tr>
      {rows}
    </table>
    </body></html>
    """


# ---------------------------------------------------------------------------
# Russell 2000
# ---------------------------------------------------------------------------

class TestGetRussell2000Tickers:

    def test_returns_equity_tickers_only(self):
        with patch("app.screener.universe.requests.get", return_value=_mock_vanguard_response(["AAPL", "MSFT", "GOOG"])):
            with pytest.raises(UniverseScrapeError, match="1500"):
                # Solo 3 tickers → debe fallar la validación de mínimo
                get_russell2000_tickers()

    def test_raises_on_http_error(self):
        with patch("app.screener.universe.requests.get", side_effect=Exception("Connection refused")):
            with pytest.raises(UniverseScrapeError, match="Vanguard"):
                get_russell2000_tickers()

    def test_retries_once_on_transient_error_then_succeeds(self):
        tickers = [f"TK{i:04d}" for i in range(1600)]
        with patch(
            "app.screener.universe.requests.get",
            side_effect=[TimeoutError("Read timed out"), _mock_vanguard_response(tickers, include_blank=False)],
        ):
            result = get_russell2000_tickers()
        assert len(result) == 1600

    def test_raises_when_no_entities(self):
        empty = _mock_response("", json_data={"size": 0, "fund": {"entity": []}})
        with patch("app.screener.universe.requests.get", return_value=empty):
            with pytest.raises(UniverseScrapeError, match="sin holdings"):
                get_russell2000_tickers()

    def test_filters_out_blank_tickers(self):
        """Filas sin ticker (p.ej. posiciones de cash) deben excluirse del resultado."""
        tickers = [f"TK{i:04d}" for i in range(1600)]
        with patch("app.screener.universe.requests.get", return_value=_mock_vanguard_response(tickers, include_blank=True)):
            result = get_russell2000_tickers()
        assert "" not in result
        assert all(t.startswith("TK") for t in result)
        assert len(result) == 1600

    def test_dot_converted_to_dash(self):
        """Tickers con punto (p.ej. BRK.A) deben convertirse a BRK-A."""
        tickers = ["BRK.A", "BRK.B"] + [f"TK{i:04d}" for i in range(1598)]
        with patch("app.screener.universe.requests.get", return_value=_mock_vanguard_response(tickers, include_blank=False)):
            result = get_russell2000_tickers()
        assert "BRK-A" in result
        assert "BRK-B" in result
        assert "BRK.A" not in result

    def test_returns_sorted_deduplicated_list(self):
        tickers = [f"TK{i:04d}" for i in range(1600)] + ["TK0001"]  # duplicado intencional
        with patch("app.screener.universe.requests.get", return_value=_mock_vanguard_response(tickers, include_blank=False)):
            result = get_russell2000_tickers()
        assert result == sorted(set(result))
        assert len(result) == 1600  # deduplicado


# ---------------------------------------------------------------------------
# European index scraping
# ---------------------------------------------------------------------------

class TestScrapeEuropeanIndex:

    def test_adds_exchange_suffix(self):
        html = _make_wikipedia_html("Ticker", ["MC", "TTE", "BNP", "AI", "SAN"] * 10)
        with patch("app.screener.universe.requests.get", return_value=_mock_response(html)):
            result = _scrape_european_index(
                "https://en.wikipedia.org/wiki/CAC_40", ["Ticker"], ".PA", min_tickers=30
            )
        assert all(t.endswith(".PA") for t in result)
        assert "MC.PA" in result

    def test_does_not_duplicate_suffix(self):
        """Si el ticker ya tiene sufijo, no añadir otro."""
        html = _make_wikipedia_html("Ticker", ["MC.PA", "TTE.PA"] + ["X"] * 30)
        with patch("app.screener.universe.requests.get", return_value=_mock_response(html)):
            result = _scrape_european_index(
                "https://en.wikipedia.org/wiki/CAC_40", ["Ticker"], ".PA", min_tickers=10
            )
        # MC.PA ya tenía sufijo → no debe quedar MC.PA.PA
        assert "MC.PA.PA" not in result
        assert "MC.PA" in result

    def test_tries_fallback_column_names(self):
        """Prueba columnas alternativas si la primera no existe."""
        html = _make_wikipedia_html("Symbol", ["AZN", "HSBA", "BP"] * 35)
        with patch("app.screener.universe.requests.get", return_value=_mock_response(html)):
            result = _scrape_european_index(
                "https://en.wikipedia.org/wiki/FTSE_100_Index",
                ["EPIC", "Symbol"],  # EPIC no existe → debe probar Symbol
                ".L",
                min_tickers=30,
            )
        assert "AZN.L" in result

    def test_returns_empty_list_on_http_error(self):
        with patch("app.screener.universe.requests.get", side_effect=Exception("timeout")):
            result = _scrape_european_index(
                "https://en.wikipedia.org/wiki/CAC_40", ["Ticker"], ".PA", min_tickers=10
            )
        assert result == []

    def test_returns_empty_list_when_column_not_found(self):
        html = _make_wikipedia_html("SomeOtherColumn", ["X"] * 50)
        with patch("app.screener.universe.requests.get", return_value=_mock_response(html)):
            result = _scrape_european_index(
                "https://en.wikipedia.org/wiki/CAC_40", ["Ticker", "Symbol"], ".PA", min_tickers=10
            )
        assert result == []

    def test_returns_empty_when_too_few_tickers(self):
        """Si hay menos de min_tickers, la tabla no es válida."""
        html = _make_wikipedia_html("Ticker", ["MC", "TTE"])
        with patch("app.screener.universe.requests.get", return_value=_mock_response(html)):
            result = _scrape_european_index(
                "https://en.wikipedia.org/wiki/CAC_40", ["Ticker"], ".PA", min_tickers=30
            )
        assert result == []

    def test_deduplicates_result(self):
        tickers = ["MC", "MC", "TTE", "BNP"] * 12  # duplicados intencionales
        html = _make_wikipedia_html("Ticker", tickers)
        with patch("app.screener.universe.requests.get", return_value=_mock_response(html)):
            result = _scrape_european_index(
                "https://en.wikipedia.org/wiki/CAC_40", ["Ticker"], ".PA", min_tickers=10
            )
        assert len(result) == len(set(result))
