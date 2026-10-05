from datetime import date

from app.screener.sec_edgar import _extract_eps, _extract_quality, _extract_supply


def _fact(start, end, value, filed, form="10-K"):
    item = {"end": end, "val": value, "filed": filed, "form": form}
    if start is not None:
        item["start"] = start
    return item


def _facts(eps_units=None, **tags):
    gaap = dict(tags)
    if eps_units is not None:
        gaap["EarningsPerShareDiluted"] = {"units": {"USD/shares": eps_units}}
    return {"facts": {"us-gaap": gaap, "dei": {}}}


def test_eps_reconstructs_q4_from_10k_and_keeps_ttm_quarterly():
    units = [
        _fact("2025-01-01", "2025-03-31", 1.0, "2025-05-01", "10-Q"),
        _fact("2025-04-01", "2025-06-30", 2.0, "2025-08-01", "10-Q"),
        _fact("2025-07-01", "2025-09-30", 3.0, "2025-11-01", "10-Q"),
        _fact("2025-01-01", "2025-12-31", 10.0, "2026-02-01", "10-K"),
    ]
    result = _extract_eps(_facts(units))
    assert result.quarterly[-1] == 4.0
    assert sum(result.quarterly[-4:]) == 10.0


def test_eps_reconstructs_q4_for_non_calendar_fiscal_year():
    units = [
        _fact("2025-07-01", "2025-09-30", 1.0, "2025-11-01", "10-Q"),
        _fact("2025-10-01", "2025-12-31", 2.0, "2026-02-01", "10-Q"),
        _fact("2026-01-01", "2026-03-31", 3.0, "2026-05-01", "10-Q"),
        _fact("2025-07-01", "2026-06-30", 10.0, "2026-08-01", "10-K"),
    ]
    result = _extract_eps(_facts(units))
    assert result.quarterly[-1] == 4.0


def test_supply_deduplicates_amended_facts_by_period():
    units = {
        "EntityCommonStockSharesOutstanding": {
            "units": {"shares": [
                _fact(None, "2024-09-30", 400, "2024-10-01"),
                _fact(None, "2024-12-31", 300, "2025-01-01"),
                _fact(None, "2024-12-31", 250, "2025-02-01"),
                _fact(None, "2025-03-31", 200, "2025-04-01"),
                _fact(None, "2025-03-31", 100, "2025-05-01"),
                _fact(None, "2025-06-30", 90, "2025-07-01"),
                _fact(None, "2025-09-30", 90, "2025-10-01"),
                _fact(None, "2025-12-31", 80, "2026-01-01"),
                _fact(None, "2026-03-31", 70, "2026-04-01"),
            ]}
        }
    }
    result = _extract_supply({"facts": {"dei": units, "us-gaap": {}}}, 4)
    # Four distinct periods back from 2026-03-31 is 2025-03-31 (100 shares),
    # rather than an amended 2024-12-31 fact being counted as a quarter.
    assert result.shares_outstanding_change_pct == (70 - 100) / 100


def test_quality_aligns_same_fiscal_year_and_reads_instant_equity():
    def annual(tag, values):
        return {tag: {"units": {"USD": [
            _fact(f"{year}-01-01", f"{year}-12-31", value, f"{year + 1}-02-01")
            for year, value in values
        ]}}}

    facts = _facts(
        **annual("GrossProfit", [(2023, 40), (2024, 50), (2025, 60)]),
        **annual("Revenues", [(2023, 100), (2024, 100), (2025, 100)]),
        **annual("NetIncomeLoss", [(2023, 10), (2024, 12), (2025, 15)]),
        StockholdersEquity={"units": {"USD": [
            _fact(None, "2025-12-31", 100, "2026-02-01"),
        ]}},
    )
    result = _extract_quality(facts)
    assert result.gross_margin == 0.5
    assert result.net_margin == 0.12333333333333334
    assert result.roe == 0.15
