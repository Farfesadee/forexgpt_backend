"""
Integration Tests
================================
Tests the complete flow across all three services:
    1. CodeGen generates a strategy
    2. Backtest runs that strategy
    3. Mentor analyzes the poor results via start_backtest_conversation()
    4. CodeGen improves the strategy based on feedback
    5. Backtest runs the improved strategy

NOTE: These tests require:
    - Supabase credentials correctly set in .env
    - All three services (mentor, codegen, backtest) fully implemented

Run with:
    python -m pytest tests/test_integration.py -v
"""

from core.database import db
from core.hf_client import mistral_client
from models.mentor import BacktestContext
from services.backtest_service import BacktestService
from services.codegen_service import CodeGenService
from services.mentor_service import MentorService
import pytest
import pytest_asyncio

# Mark every async test in this file as an asyncio test automatically.
# Required because pytest-asyncio is running in STRICT mode on this project.
pytestmark = pytest.mark.asyncio


# mistral_client — used by both MentorService and CodeGenService

# db — the Database singleton that exposes db.mentor, db.backtests etc.
# This is what the services expect, NOT the raw Supabase Client from get_db()


# Shared fixtures

@pytest.fixture
def user_id():
    """
    A valid UUID for the test user.
    Must be a proper UUID string
    create the user via Supabase or endpoint
    dashboard first and paste their UUID here.
    """
    return "ceabb23f-ca80-4fd7-a811-40c3a03ad375"  # Add the user ID here, a valid one


@pytest.fixture
def sample_backtest_results():
    """
    A sample poor-performing backtest result dict.
    Field names match what BacktestService.run_custom_strategy() actually returns.
    """
    return {
        "sharpe_ratio":     0.3,
        "max_drawdown_pct": 18.5,
        "win_rate_pct":     45.2,
        "total_return_pct": -5.3,
        "total_trades":     42,
    }


@pytest.fixture
def sample_strategy_code():
    """
    A minimal but fully self-contained RSI mean reversion strategy.
    Must define generate_signals(data) — BacktestService validates for this
    before executing any code.
    """
    return """
def generate_signals(data):
    import pandas as pd

    close = data['close']
    delta = close.diff()
    gain  = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rsi   = 100 - (100 / (1 + gain / loss))

    signals = []
    for r in rsi:
        if r < 30:
            signals.append(1)
        elif r > 70:
            signals.append(-1)
        else:
            signals.append(0)
    return signals
"""


@pytest.fixture
def sample_backtest_context(sample_backtest_results):
    """
    A BacktestContext object built from the sample results.
    MentorService.start_backtest_conversation() requires this object —
    it cannot receive a plain dict.
    """
    return BacktestContext(
        strategy_type="custom",
        metrics=sample_backtest_results,
    )


# Individual service checks

@pytest.mark.asyncio
async def test_mentor_analyzes_backtest_results(user_id, sample_backtest_context):
    """
    Verify MentorService can receive a BacktestContext and return
    a meaningful educational analysis via start_backtest_conversation().
    """
    mentor = MentorService(mistral_client, db)

    result = await mentor.start_backtest_conversation(
        user_id=user_id,
        backtest_context=sample_backtest_context,
    )

    assert result is not None, "Mentor should return a result dict"
    assert "analysis" in result, "Result should contain an 'analysis' key"
    assert len(result["analysis"]
               ) > 100, "Analysis should be a substantial response"
    assert "conversation_id" in result, "Result should contain a conversation_id for follow-ups"


@pytest.mark.asyncio
async def test_codegen_improves_strategy(user_id, sample_strategy_code, sample_backtest_results):
    """
    Verify CodeGenService can take an original strategy + backtest results
    + mentor analysis and return an improved version of the code.
    """
    codegen = CodeGenService(mistral_client)

    # Simulating the mentor analysis string —
    # in the real flow this comes from start_backtest_conversation()
    mentor_analysis = (
        "The strategy failed because it trades into strong trends. "
        "Mean reversion does not work when the market is trending. "
        "Add an ADX filter to avoid trending conditions and a stop loss "
        "to cap the maximum loss per trade."
    )

    result = await codegen.generate_improvement(
        user_id=user_id,
        original_code=sample_strategy_code,
        backtest_results=sample_backtest_results,
        mentor_analysis=mentor_analysis,
    )

    assert result is not None, "CodeGen should return a result dict"
    assert result.get(
        "code") is not None, "Result should contain improved code"
    assert len(result["code"]) > len(sample_strategy_code), (
        "Improved code should be longer than the original — improvements were added"
    )


@pytest.mark.asyncio
async def test_backtest_runs_custom_strategy(user_id, sample_strategy_code):
    """
    Verify BacktestService can safely execute a custom strategy
    and return valid performance metrics.
    """
    backtest = BacktestService()

    results = await backtest.run_custom_strategy(
        user_id=user_id,
        custom_code=sample_strategy_code,
        pair="EURUSD",
        start_date="2023-01-01",
        end_date="2023-12-31",
        initial_capital=10000.0,
        position_size_pct=0.1,
    )

    assert results is not None, "Backtest should return a results dict"
    assert results.get(
        "sharpe_ratio") is not None, "Sharpe ratio should be calculated"
    assert results.get(
        "max_drawdown_pct") is not None, "Max drawdown should be calculated"
    assert results.get(
        "win_rate_pct") is not None, "Win rate should be calculated"
    assert results.get(
        "total_trades") is not None, "Total trades should be counted"


# Full end-to-end flow

@pytest.mark.asyncio
async def test_complete_flow(user_id, sample_strategy_code):
    """
    Full end-to-end integration test across all three services:
        1. CodeGen generates a strategy
        2. Backtest runs that strategy
        3. If Sharpe < 1.0, Mentor analyzes results via start_backtest_conversation()
        4. CodeGen improves the strategy based on mentor feedback
        5. Backtest runs the improved strategy and we compare results

    This is the core loop of ForexGPT — generate, test, learn, improve.
    """
    mentor = MentorService(mistral_client, db)
    codegen = CodeGenService(mistral_client)
    backtest = BacktestService()

    # Step 1: Generate an initial strategy from a plain description
    code_result = await codegen.generate_code(
        user_id=user_id,
        strategy_description="Create a simple RSI mean reversion strategy",
    )

    assert code_result.get(
        "code") is not None, "Step 1 failed: CodeGen returned no code"
    original_code = code_result["code"]

    # Step 2: Run the generated code through the backtest engine
    backtest_results = await backtest.run_custom_strategy(
        user_id=user_id,
        custom_code=original_code,
        pair="EURUSD",
        start_date="2023-01-01",
        end_date="2023-12-31",
        initial_capital=10000.0,
        position_size_pct=0.1,
    )

    assert backtest_results.get("sharpe_ratio") is not None, (
        "Step 2 failed: Backtest returned no Sharpe ratio"
    )

    # Steps 3-5 only run if the strategy performed poorly
    if backtest_results["sharpe_ratio"] < 1.0:

        # Step 3: Build a BacktestContext and let Mentor analyse what went wrong
        context = BacktestContext(
            strategy_type="mean_reversion",
            metrics=backtest_results,
        )

        mentor_result = await mentor.start_backtest_conversation(
            user_id=user_id,
            backtest_context=context,
        )

        assert mentor_result.get("analysis") is not None, (
            "Step 3 failed: Mentor returned no analysis"
        )
        assert len(mentor_result["analysis"]) > 100, (
            "Step 3 failed: Mentor analysis is too short to be useful"
        )

        # Step 4: Feed original code + results + mentor analysis to CodeGen and ask it to produce an improved version
        improved_result = await codegen.generate_improvement(
            user_id=user_id,
            original_code=original_code,
            backtest_results=backtest_results,
            mentor_analysis=mentor_result["analysis"],
        )

        assert improved_result.get("code") is not None, (
            "Step 4 failed: CodeGen returned no improved code"
        )
        improved_code = improved_result["code"]

        # Step 5: Backtest the improved strategy and compare against the original
        improved_backtest = await backtest.run_custom_strategy(
            user_id=user_id,
            custom_code=improved_code,
            pair="EURUSD",
            start_date="2023-01-01",
            end_date="2023-12-31",
            initial_capital=10000.0,
            position_size_pct=0.1,
        )

        assert improved_backtest.get("sharpe_ratio") is not None, (
            "Step 5 failed: Improved backtest returned no Sharpe ratio"
        )

        # Side-by-side comparison in the test output
        print("\n--- Performance Comparison ---")
        print(
            f"Original  → Sharpe: {backtest_results['sharpe_ratio']:.2f} | "
            f"Drawdown: {backtest_results['max_drawdown_pct']:.2f}%"
        )
        print(
            f"Improved  → Sharpe: {improved_backtest['sharpe_ratio']:.2f} | "
            f"Drawdown: {improved_backtest['max_drawdown_pct']:.2f}%"
        )

    else:
        # Strategy performed well on first try — no improvement loop needed
        print(
            f"\nStrategy Sharpe of {backtest_results['sharpe_ratio']:.2f} "
            f"is already above 1.0 — no improvement loop triggered."
        )
