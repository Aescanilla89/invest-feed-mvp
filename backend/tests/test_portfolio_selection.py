from app.core.config import Settings
from app.jobs import update_portfolio


def test_mean_reversion_is_disabled_by_default():
    original = update_portfolio.settings.portfolio_enable_mean_reversion
    try:
        update_portfolio.settings.portfolio_enable_mean_reversion = False
        assert "mean_reversion" not in update_portfolio._enabled_portfolio_methods()
    finally:
        update_portfolio.settings.portfolio_enable_mean_reversion = original


def test_mean_reversion_can_be_reenabled_explicitly():
    original = update_portfolio.settings.portfolio_enable_mean_reversion
    try:
        update_portfolio.settings.portfolio_enable_mean_reversion = True
        assert "mean_reversion" in update_portfolio._enabled_portfolio_methods()
    finally:
        update_portfolio.settings.portfolio_enable_mean_reversion = original
