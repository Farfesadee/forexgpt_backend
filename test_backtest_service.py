"""
tests/test_backtest_service.py
Tests BacktestService with:
  - Mocked Supabase (no real DB needed)
  - Mocked DataFetcher (no network calls, tests run fast and reliably)
Run with: pytest tests/test_backtest_service.py -v -s
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from services.backtest_service import BacktestService


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_price_data(n=500, start="2021-01-01") -> pd.DataFrame:
    """
    Generate realistic synthetic OHLCV data.
    Used to mock DataFetcher so tests never make network calls.
    """
    dates  = pd.date_range(start=start, periods=n, freq="B")  # business days
    np.random.seed(42)
    close  = 1.1 + np.cumsum(np.random.randn(n) * 0.003)      # EUR/USD-like prices
    spread = 0.001

    df = pd.DataFrame({
        "date":   dates,
        "open":   close + np.random.uniform(-spread, spread, n),
        "high":   close + np.random.uniform(0, spread * 2, n),
        "low":    close - np.random.uniform(0, spread * 2, n),
        "close":  close,
        "volume": np.zeros(n)
    })
    return df


# ── Mock setup ────────────────────────────────────────────────────────────────

# Mock Supabase — simulates a successful DB insert
mock_db = MagicMock()
mock_db.table.return_value.insert.return_value.execute.return_value.data = [
    {"id": "test-uuid-123", "created_at": "2024-01-01T00:00:00+00:00"}
]

service = BacktestService(db=mock_db)

# Synthetic price data used by all tests
PRICE_DATA = make_price_data(n=600, start="2021-01-01")


# ── Test 1: RSI strategy, save_to_db=True ─────────────────────────────────────

@pytest.mark.asyncio
async def test_run_backtest_rsi():
    """RSI strategy runs end-to-end and returns correct structure."""
    with patch("services.backtest_service.DataFetcher") as MockFetcher:
        MockFetcher.return_value.fetch.return_value = PRICE_DATA.set_index("date")

        result = await service.run_backtest(
            user_id="test-user",
            symbol="EURUSD",
            strategy="rsi",
            start="2021-01-01",
            end="2023-06-30",
            initial_capital=10000,
            save_to_db=True
        )

    assert result["symbol"]        == "EURUSD"
    assert result["strategy_name"] == "rsi"
    assert result["backtest_id"]   == "test-uuid-123"
    assert result["metrics"]       is not None

    m = result["metrics"]
    for key in ["total_return_pct", "sharpe_ratio", "max_drawdown_pct",
                "total_trades", "win_rate_pct", "profit_factor", "total_costs"]:
        assert key in m, f"Missing metric: {key}"

    print(f"\n  Return   : {m['total_return_pct']}%")
    print(f"  CAGR     : {m['cagr_pct']}%")
    print(f"  Sharpe   : {m['sharpe_ratio']}")
    print(f"  Drawdown : {m['max_drawdown_pct']}%")
    print(f"  Trades   : {m['total_trades']}")
    print(f"  Win Rate : {m['win_rate_pct']}%")
    print(f"  Costs    : ${m['total_costs']}")


# ── Test 2: MACD strategy, save_to_db=False ───────────────────────────────────

@pytest.mark.asyncio
async def test_run_backtest_save_false():
    """save_to_db=False should skip DB and return None for backtest_id."""
    with patch("services.backtest_service.DataFetcher") as MockFetcher:
        MockFetcher.return_value.fetch.return_value = PRICE_DATA.set_index("date")

        result = await service.run_backtest(
            user_id="test-user",
            symbol="GBPUSD",
            strategy="macd",
            start="2021-01-01",
            end="2023-06-30",
            initial_capital=5000,
            save_to_db=False
        )

    assert result["backtest_id"]              is None
    assert result["symbol"]                   == "GBPUSD"
    assert result["metrics"]                  is not None
    assert result["metrics"]["initial_capital"] == 5000.0


# ── Test 3: Invalid strategy raises ValueError before fetching data ───────────

@pytest.mark.asyncio
async def test_invalid_strategy():
    """Unknown strategy name should raise ValueError."""
    with patch("services.backtest_service.DataFetcher") as MockFetcher:
        MockFetcher.return_value.fetch.return_value = PRICE_DATA.set_index("date")

        with pytest.raises(ValueError, match="Unknown strategy"):
            await service.run_backtest(
                user_id="test-user",
                symbol="EURUSD",
                strategy="fake_strategy",
                start="2021-01-01",
                end="2023-06-30",
                save_to_db=False
            )


# ── Test 4: All four strategies complete without error ────────────────────────

@pytest.mark.asyncio
async def test_all_strategies():
    """All four strategies run and return valid metrics."""
    strategies = [
        ("rsi",                      {"period": 14, "oversold": 30, "overbought": 70}),
        ("macd",                     {"fast": 12, "slow": 26, "signal": 9}),
        ("bollinger_bands",          {"period": 20, "std_dev": 2.0}),
        ("moving_average_crossover", {"fast_period": 50, "slow_period": 200}),
    ]

    print()
    with patch("services.backtest_service.DataFetcher") as MockFetcher:
        MockFetcher.return_value.fetch.return_value = PRICE_DATA.set_index("date")

        for strategy, params in strategies:
            result = await service.run_backtest(
                user_id="test-user",
                symbol="EURUSD",
                strategy=strategy,
                start="2021-01-01",
                end="2023-06-30",
                strategy_params=params,
                save_to_db=False
            )
            m = result["metrics"]
            assert m is not None
            print(
                f"  {strategy:<30} "
                f"trades={m['total_trades']:>4}  "
                f"return={m['total_return_pct']:>7.2f}%  "
                f"sharpe={m['sharpe_ratio']:>6.3f}"
            )
