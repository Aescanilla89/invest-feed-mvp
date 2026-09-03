from unittest.mock import MagicMock, patch

import pytest

from app.screener.fear_greed import FearGreedFetchError, get_fear_greed_index


def _mock_response(json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    return resp


def _payload(score: float = 36.3, rating: str = "fear") -> dict:
    return {
        "fear_and_greed": {
            "score": score,
            "rating": rating,
            "timestamp": "2026-09-03T13:47:38+00:00",
            "previous_close": 33.2,
            "previous_1_week": 55.4,
            "previous_1_month": 50.7,
            "previous_1_year": 61.3,
        },
        "fear_and_greed_historical": {
            "data": [
                {"x": 1756857600000.0, "y": 61.3, "rating": "greed"},
                {"x": 1756944000000.0, "y": 58.6, "rating": "greed"},
            ],
        },
    }


class TestGetFearGreedIndex:

    def test_parses_current_score_and_rating(self):
        with patch("app.screener.fear_greed.requests.get", return_value=_mock_response(_payload())):
            result = get_fear_greed_index()
        assert result.score == 36.3
        assert result.rating == "fear"
        assert result.previous_1_week == 55.4

    def test_parses_history_as_iso_dates(self):
        with patch("app.screener.fear_greed.requests.get", return_value=_mock_response(_payload())):
            result = get_fear_greed_index()
        assert len(result.history) == 2
        assert result.history[0].date == "2025-09-03"
        assert result.history[0].score == 61.3
        assert result.history[0].rating == "greed"

    def test_history_truncated_to_history_days(self):
        payload = _payload()
        payload["fear_and_greed_historical"]["data"] = [
            {"x": 1756857600000.0 + i * 86_400_000, "y": float(i), "rating": "neutral"} for i in range(50)
        ]
        with patch("app.screener.fear_greed.requests.get", return_value=_mock_response(payload)):
            result = get_fear_greed_index(history_days=10)
        assert len(result.history) == 10
        assert result.history[-1].score == 49.0  # el más reciente

    def test_raises_on_missing_score(self):
        with patch("app.screener.fear_greed.requests.get", return_value=_mock_response({"fear_and_greed": {}})):
            with pytest.raises(FearGreedFetchError):
                get_fear_greed_index()

    def test_raises_on_http_error(self):
        with patch("app.screener.fear_greed.requests.get", side_effect=Exception("418 I'm a teapot")):
            with pytest.raises(Exception, match="teapot"):
                get_fear_greed_index()
