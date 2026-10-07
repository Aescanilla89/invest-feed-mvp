from datetime import date, timedelta

from app.market_desk import (
    Indicator,
    MarketDeskResponse,
    _cross_asset,
    composite_score,
    _fred_indicator,
    _horizon_change,
    _sofr_spread_indicator,
    build_market_desk,
    classify_macro,
    regime_label,
    weighted_score,
)


def test_regime_thresholds_are_exclusive_and_complete():
    assert regime_label(0) == "STRESS"
    assert regime_label(19.9) == "STRESS"
    assert regime_label(20) == "RISK-OFF"
    assert regime_label(40) == "NEUTRAL"
    assert regime_label(60) == "RISK-ON"
    assert regime_label(80) == "STRONG RISK-ON"
    assert regime_label(100) == "STRONG RISK-ON"
    assert regime_label(None) == "PARTIAL DATA"


def test_weighted_score_renormalizes_only_available_inputs():
    rows = [Indicator(key="x", label="x", value=1, frequency="daily", source="test", interpretation="", score=80),
            Indicator(key="y", label="y", value=None, frequency="daily", source="test", interpretation="")]
    assert weighted_score(rows, {"x": 1, "y": 3}) == 80
    assert weighted_score(rows[1:], {"y": 1}) is None
    assert composite_score([(80,.3),(None,.3),(None,.2),(None,.2)]) is None
    assert composite_score([(80,.3),(60,.7),(None,.2),(None,.2)]) == 66.0


def test_stale_observations_remain_visible_but_do_not_score():
    old = (date.today() - timedelta(days=90)).isoformat()
    item = _fred_indicator("VIXCLS", {"VIXCLS": [(old, 15.0), ((date.today()-timedelta(days=89)).isoformat(), 16.0)]})
    assert item.value == 16.0
    assert item.freshness == "old"
    assert item.score is None


def test_stress_levels_use_level_not_only_recent_direction():
    history=[((date.today()-timedelta(days=6-i)).isoformat(),50.0-i*2) for i in range(6)]
    item=_fred_indicator("VIXCLS",{"VIXCLS":history})
    assert item.value==40.0
    assert item.score==0


def test_sofr_funding_signal_is_relative_to_effr_not_nominal_level():
    days=[(date.today()-timedelta(days=5-i)).isoformat() for i in range(6)]
    high_policy={"SOFR":[(d,5.50) for d in days],"EFFR":[(d,5.47) for d in days]}
    low_policy={"SOFR":[(d,3.90) for d in days],"EFFR":[(d,3.87) for d in days]}
    assert _fred_indicator("SOFR",high_policy).score is None
    assert _sofr_spread_indicator(high_policy).score==80
    assert _sofr_spread_indicator(low_policy).score==80
    wider={"SOFR":[(d,3.95) for d in days],"EFFR":[(d,3.85) for d in days]}
    assert _sofr_spread_indicator(wider).score==52


def test_price_index_without_year_of_history_is_excluded():
    points=[((date.today()-timedelta(days=30*(5-i))).isoformat(),100.0+i) for i in range(6)]
    item=_fred_indicator("CPILFESL",{"CPILFESL":points})
    assert item.value is None
    assert item.score is None
    assert "Insufficient history" in item.interpretation


def test_horizon_change_uses_matching_observation_window():
    points = [((date.today()-timedelta(days=35-i*7)).isoformat(), float(i)) for i in range(6)]
    assert _horizon_change(points, 7, 12) == 1.0
    assert _horizon_change(points, 30, 12) == 5.0
    assert _horizon_change(points, 1, 1) is None


def test_macro_regime_classification_uses_both_axes():
    def ind(key, value, change):
        return Indicator(key=key, label=key, value=value, previous=value-change, change=change, as_of=date.today().isoformat(), frequency="monthly", freshness="fresh", source="FRED", interpretation="", score=50)
    assert classify_macro([ind("INDPRO", 2, .2), ind("CPILFESL", 3, -.1)]).regime == "GOLDILOCKS"
    assert classify_macro([ind("INDPRO", 2, .2), ind("CPILFESL", 3, .1)]).regime == "REFLATION"
    assert classify_macro([ind("INDPRO", -1, -.2), ind("CPILFESL", 3, -.1)]).regime == "SLOWDOWN"
    assert classify_macro([ind("INDPRO", -1, -.2), ind("CPILFESL", 3, .1)]).regime == "STAGFLATION"
    assert classify_macro([]).regime == "INSUFFICIENT DATA"


def test_cross_asset_equity_credit_divergence_is_explicit():
    items = [
        Indicator(key="SPY", label="SPY", value=600, change=1.0, frequency="daily", source="Alpaca", interpretation="", score=75),
        Indicator(key="BAMLH0A0HYM2", label="HY", value=4.2, change=.2, frequency="daily", source="FRED", interpretation="", score=30),
    ]
    result = _cross_asset(items, {"liquidity": None, "stress": 30})
    assert result[0].title == "Equity-credit divergence"


def test_missing_providers_never_return_a_fabricated_market_score(monkeypatch):
    monkeypatch.setattr("app.market_desk._fetch_fred", lambda: {})
    monkeypatch.setattr("app.market_desk._alpaca_internals", lambda: [])
    response = build_market_desk()
    assert response.market_regime.score is None
    assert response.market_regime.label == "PARTIAL DATA"
    assert response.confidence == 0
    assert response.coverage == {"available": 0, "expected": 25}
    assert response.liquidity.score is None
    assert response.stress.score is None
    assert response.market_internals.score is None
    # Pydantic schema validation is part of the API contract.
    assert MarketDeskResponse.model_validate(response.model_dump())


def test_market_desk_route_returns_schema_even_if_calendar_db_is_unavailable(monkeypatch):
    from app.api.routes import market_desk as route
    monkeypatch.setattr(route, "get_market_desk", lambda: build_market_desk())

    class UnavailableDB:
        def query(self, *_args): raise RuntimeError("calendar database unavailable")

    result = route.market_desk(UnavailableDB())
    assert isinstance(result, MarketDeskResponse)
    assert result.watch_next == []


def test_market_desk_is_exposed_in_fastapi_openapi_with_typed_response():
    from app.main import app
    operation=app.openapi()["paths"]["/api/market-desk"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("MarketDeskResponse")
