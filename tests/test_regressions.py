import pandas as pd
import pytest

from backtesting.data_fetcher import DataFetcher
from services.backtest_service import _build_strategy
from services.codegen_service import CodeGenService


class DummyCodeGenService(CodeGenService):
    def __init__(self):
        super().__init__(mistral_client=None)
        self.captured_kwargs = None

    async def generate_code(self, **kwargs):
        self.captured_kwargs = kwargs
        return kwargs


@pytest.mark.asyncio
async def test_generate_improvement_persists_clean_summary():
    service = DummyCodeGenService()

    result = await service.generate_improvement(
        user_id="user-123",
        original_code="def generate_signals(data):\n    return [0] * len(data)",
        backtest_results={
            "strategy_name": "custom",
            "pair": "EURUSD",
            "total_return_pct": -12.5,
        },
        mentor_analysis="Add a trend filter and stronger exits.",
        additional_requirements="Keep the strategy simple",
    )

    assert result["strategy_description"].startswith("Improve my custom strategy for EURUSD")
    assert "EXPERT ANALYSIS:" in result["llm_user_message"]
    assert result["stored_user_message"] == result["strategy_description"]
    assert result["stored_description"] == result["strategy_description"]
    assert "Add a trend filter" not in result["stored_description"]


def test_yfinance_auto_formats_unknown_forex_pair():
    fetcher = DataFetcher()
    assert fetcher._to_yfinance_ticker("GBPJPY") == "GBPJPY=X"
    assert fetcher._to_yfinance_ticker("EUR/USD") == "EURUSD=X"


def test_sma_defaults_can_trigger_with_documented_shorter_windows():
    strategy = _build_strategy("sma", {})
    data = pd.DataFrame(
        {
            "close": ([1.0] * 30) + [10.0],
        }
    )

    signal, reason = strategy(data)

    assert signal == "buy"
    assert "MA10" in reason
    assert "MA30" in reason


def test_sma_alias_params_are_respected():
    strategy = _build_strategy("moving_average_crossover", {"fast": 3, "slow": 5})
    data = pd.DataFrame(
        {
            "close": [1.0, 1.0, 1.0, 1.0, 1.0, 10.0],
        }
    )

    signal, reason = strategy(data)

    assert signal == "buy"
    assert "MA3" in reason
    assert "MA5" in reason
