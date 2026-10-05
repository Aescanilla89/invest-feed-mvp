from app.screener.data_source import DividendData, FundamentalData
from app.screener.strategies import evaluate_dividendos


def test_dividend_strategy_requires_positive_eps():
    result = evaluate_dividendos(
        DividendData(yield_pct=0.04, payout_ratio=0.5, annual_dividend=2.0),
        FundamentalData(None, None, [], [-1.0]),
    )
    assert result.passed is False


def test_dividend_strategy_returns_none_without_eps():
    result = evaluate_dividendos(
        DividendData(yield_pct=0.04, payout_ratio=0.5, annual_dividend=2.0),
        FundamentalData(None, None, [], []),
    )
    assert result.passed is None
    assert "no disponible" in result.details
