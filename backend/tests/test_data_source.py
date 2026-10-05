from unittest.mock import Mock


def test_alpaca_data_source_uses_alpaca_corporate_actions_module(monkeypatch):
    import alpaca.data.historical as historical
    import alpaca.data.historical.corporate_actions as corporate_actions

    stock_client = Mock()
    corporate_client = Mock()
    monkeypatch.setattr(historical, "StockHistoricalDataClient", lambda *args: stock_client)
    monkeypatch.setattr(corporate_actions, "CorporateActionsClient", lambda *args: corporate_client)

    from app.screener.data_source import AlpacaDataSource

    source = AlpacaDataSource("key", "secret")

    assert source._client is stock_client
    assert source._corporate_actions is corporate_client
