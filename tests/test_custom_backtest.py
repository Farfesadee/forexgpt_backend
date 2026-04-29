"""
tests/test_custom_backtest.py
=============================================================
Three-stage test for the custom backtest feature.
Run BEFORE connecting to the frontend.

STAGE 1 — Unit tests (no Supabase, no network)
STAGE 2 — Service integration test (hits Supabase + CSV)
STAGE 3 — curl commands for endpoint testing

HOW TO RUN:
    # Stage 1 only (fast, no DB needed):
    python -m pytest tests/test_custom_backtest.py::TestValidation -v
    python -m pytest tests/test_custom_backtest.py::TestSandbox -v

    # Stage 2 (needs uvicorn running and Supabase connected):
    python tests/test_custom_backtest.py

    # Stage 3: copy-paste curl commands from bottom of this file
=============================================================
"""

import asyncio
import pytest
import pandas as pd
import numpy as np
import sys
import os

# Make sure project root is on path when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.backtest_service import BacktestService

service = BacktestService()


# =============================================================================
# STAGE 1A — _validate_code_safety() unit tests
# Run with: python -m pytest tests/test_custom_backtest.py::TestValidation -v
# =============================================================================

class TestValidation:

    def test_valid_code_passes(self):
        """Well-formed code with generate_signals should not raise."""
        code = """
def generate_signals(data):
    return [1 if i % 2 == 0 else -1 for i in range(len(data))]
"""
        service._validate_code_safety(code)   # must not raise

    def test_missing_function_raises(self):
        """Code without generate_signals() must raise ValueError."""
        code = "x = 1 + 1"
        with pytest.raises(ValueError, match="generate_signals"):
            service._validate_code_safety(code)

    def test_os_system_rejected(self):
        with pytest.raises(ValueError, match="forbidden"):
            service._validate_code_safety(
                "def generate_signals(data):\n    import os; os.system('ls')"
            )

    def test_subprocess_rejected(self):
        with pytest.raises(ValueError, match="forbidden"):
            service._validate_code_safety(
                "def generate_signals(data):\n    import subprocess"
            )

    def test_eval_rejected(self):
        with pytest.raises(ValueError, match="forbidden"):
            service._validate_code_safety(
                "def generate_signals(data):\n    eval('1+1')"
            )

    def test_open_rejected(self):
        with pytest.raises(ValueError, match="forbidden"):
            service._validate_code_safety(
                "def generate_signals(data):\n    open('/etc/passwd')"
            )

    def test_code_too_large_rejected(self):
        # "x = 1\n" is 6 chars, need >10,000 chars total, so multiply by 2000
        big_code = "def generate_signals(data):\n    pass\n" + ("x = 1\n" * 2000)
        with pytest.raises(ValueError, match="10 KB"):
            service._validate_code_safety(big_code)
        
    def test_pandas_numpy_allowed(self):
        """pandas and numpy usage should pass — they are allowed."""
        code = """
import pandas as pd
import numpy as np

def generate_signals(data):
    close = data['close']
    ma = close.rolling(20).mean()
    signals = np.where(close > ma, 1, -1)
    return signals.tolist()
"""
        service._validate_code_safety(code)   # must not raise


# =============================================================================
# STAGE 1B — _execute_strategy_code() sandbox tests
# Run with: python -m pytest tests/test_custom_backtest.py::TestSandbox -v
# =============================================================================

class TestSandbox:

    def _make_price_data(self, n=50):
        """Create minimal price DataFrame for sandbox tests."""
        dates  = pd.date_range("2022-01-01", periods=n, freq="B")
        prices = 1.1000 + np.cumsum(np.random.randn(n) * 0.001)
        return pd.DataFrame({
            "date":   dates,
            "open":   prices,
            "high":   prices * 1.001,
            "low":    prices * 0.999,
            "close":  prices,
            "volume": [1000] * n,
        })

    @pytest.mark.asyncio
    async def test_simple_alternating_signals(self):
        """Strategy that alternates 1/-1 should return correct length."""
        code = """
def generate_signals(data):
    return [1 if i % 2 == 0 else -1 for i in range(len(data))]
"""
        data    = self._make_price_data(50)
        signals = await service._execute_strategy_code(code, data)

        assert len(signals) == 50
        assert int(signals.iloc[0]) == 1
        assert int(signals.iloc[1]) == -1

    @pytest.mark.asyncio
    async def test_rsi_strategy_runs(self):
        """A realistic RSI strategy should execute without error."""
        code = """
import pandas as pd

def generate_signals(data):
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
        data    = self._make_price_data(100)
        signals = await service._execute_strategy_code(code, data)

        assert len(signals) == 100
        assert set(signals.unique()).issubset({-1.0, 0.0, 1.0})

    @pytest.mark.asyncio
    async def test_dangerous_code_raises_at_execution(self):
        """
        Even if validation were bypassed, dangerous code should fail
        at execution (subprocess catches the import error).
        """
        code = """
def generate_signals(data):
    import os
    os.system('echo hacked')
    return [0] * len(data)
"""
        data = self._make_price_data(10)
        # _validate_code_safety would catch this first,
        # but _execute_strategy_code should also fail safely
        with pytest.raises(Exception):
            await service._execute_strategy_code(code, data)

    @pytest.mark.asyncio
    async def test_broken_code_raises_valueerror(self):
        """Code with a runtime error should raise ValueError with detail."""
        code = """
def generate_signals(data):
    raise RuntimeError("intentional failure")
"""
        data = self._make_price_data(20)
        with pytest.raises(ValueError, match="intentional failure"):
            await service._execute_strategy_code(code, data)


# =============================================================================
# STAGE 2 — Full service integration test
# Requires: Supabase connected + data/EURUSD.csv present
# Run with: python tests/test_custom_backtest.py
# =============================================================================

SIMPLE_RSI_CODE = """
import pandas as pd

def generate_signals(data):
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

MA_CROSSOVER_CODE = """
import pandas as pd

def generate_signals(data):
    close   = data['close']
    fast_ma = close.rolling(20).mean()
    slow_ma = close.rolling(50).mean()
    signals = []
    for i in range(len(close)):
        if i == 0:
            signals.append(0)
            continue
        if fast_ma.iloc[i] > slow_ma.iloc[i] and fast_ma.iloc[i-1] <= slow_ma.iloc[i-1]:
            signals.append(1)
        elif fast_ma.iloc[i] < slow_ma.iloc[i] and fast_ma.iloc[i-1] >= slow_ma.iloc[i-1]:
            signals.append(-1)
        else:
            signals.append(0)
    return signals
"""

# ── Replace with your actual test user UUID ───────────────────────────────────
TEST_USER_ID = "a792422a-cbb7-40e2-b7cd-f396f1c45b32"


async def run_integration_test():
    print("\n" + "=" * 60)
    print("STAGE 2 — Custom Backtest Service Integration Test")
    print("=" * 60)

    # ── Test 1: RSI strategy ──────────────────────────────────────────────────
    print("\n[1/3] Running custom RSI strategy on EURUSD...")
    try:
        result = await service.run_custom_strategy(
            user_id=TEST_USER_ID,
            custom_code=SIMPLE_RSI_CODE,
            pair="EURUSD",
            start_date="2021-01-01",
            end_date="2023-12-29",
            timeframe="1d",
            initial_capital=10000.0,
            data_source="csv",
        )
        metrics = result.get("metrics", {})
        print(f"  [OK] Status:         {result.get('status')}")
        print(f"  [OK] strategy_name:  {result.get('strategy_name')}")
        print(f"  [OK] Total trades:   {metrics.get('total_trades')}")
        print(f"  [OK] Total return:   {metrics.get('total_return_pct')}%")
        print(f"  [OK] Sharpe ratio:   {metrics.get('sharpe_ratio')}")
        print(f"  [OK] Max drawdown:   {metrics.get('max_drawdown_pct')}%")
        print(f"  [OK] Win rate:       {metrics.get('win_rate_pct')}%")
        print(f"  [OK] Backtest ID:    {result.get('id')}")
    except Exception as e:
        print(f"  [FAIL] FAILED: {e}")

    # ── Test 2: MA Crossover strategy ────────────────────────────────────────
    print("\n[2/3] Running custom MA Crossover strategy on EURUSD...")
    try:
        result = await service.run_custom_strategy(
            user_id=TEST_USER_ID,
            custom_code=MA_CROSSOVER_CODE,
            pair="EURUSD",
            start_date="2021-01-01",
            end_date="2023-12-29",
            timeframe="1d",
            initial_capital=10000.0,
            data_source="csv",
        )
        metrics = result.get("metrics", {})
        print(f"  [OK] Status:         {result.get('status')}")
        print(f"  [OK] Total trades:   {metrics.get('total_trades')}")
        print(f"  [OK] Total return:   {metrics.get('total_return_pct')}%")
        print(f"  [OK] Sharpe ratio:   {metrics.get('sharpe_ratio')}")
    except Exception as e:
        print(f"  [FAIL] FAILED: {e}")

    # ── Test 3: Dangerous code is rejected before DB row is created ───────────
    print("\n[3/3] Verifying dangerous code is rejected at validation...")
    try:
        await service.run_custom_strategy(
            user_id=TEST_USER_ID,
            custom_code="import os\nos.system('ls')",
            pair="EURUSD",
            start_date="2021-01-01",
            end_date="2023-12-29",
        )
        print("  [FAIL] FAILED — dangerous code was not rejected!")
    except ValueError as e:
        print(f"  [OK] Correctly rejected: {e}")
    except Exception as e:
        print(f"  [WARN] Unexpected error type: {e}")

    print("\n" + "=" * 60)
    print("Stage 2 complete. Check Supabase backtests table for new rows.")
    print("=" * 60 + "\n")


# =============================================================================
# STAGE 3 — curl commands (copy-paste after uvicorn is running)
# =============================================================================

CURL_COMMANDS = """
=============================================================
STAGE 3 — Endpoint Testing via curl
Run these after: uvicorn main:app --reload
Replace <YOUR_JWT_TOKEN> with a real token from your frontend login.
=============================================================

# 1. Simple RSI custom backtest
curl -X POST http://localhost:8000/api/backtest/run/custom \\
-H "Content-Type: application/json" \\
-H "Authorization: Bearer <YOUR_JWT_TOKEN>" \\
-d '{
  "user_id":          "c1d333a7-aba4-4ac7-acad-0895e798b8de",
  "pair":             "EURUSD",
  "start_date":       "2021-01-01",
  "end_date":         "2023-12-29",
  "timeframe":        "1d",
  "initial_capital":  10000,
  "position_size_pct": 0.1,
  "data_source":      "csv",
  "custom_code":      "def generate_signals(data):\\n    close = data[\\'close\\']\\n    delta = close.diff()\\n    gain = delta.where(delta > 0, 0.0).rolling(14).mean()\\n    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()\\n    rsi = 100 - (100 / (1 + gain / loss))\\n    return [1 if r < 30 else -1 if r > 70 else 0 for r in rsi]"
}'

# 2. Verify dangerous code returns 400 (not 500)
curl -X POST http://localhost:8000/api/backtest/run/custom \\
-H "Content-Type: application/json" \\
-H "Authorization: Bearer <YOUR_JWT_TOKEN>" \\
-d '{
  "user_id":     "c1d333a7-aba4-4ac7-acad-0895e798b8de",
  "pair":        "EURUSD",
  "start_date":  "2021-01-01",
  "end_date":    "2023-12-29",
  "custom_code": "import os\\nos.system(\\"ls\\")"
}'
# Expected: HTTP 400 with "forbidden operation" message

# 3. Verify existing parameterised endpoint still works (regression check)
curl -X POST http://localhost:8000/api/backtest/run \\
-H "Content-Type: application/json" \\
-H "Authorization: Bearer <YOUR_JWT_TOKEN>" \\
-d '{
  "user_id":        "c1d333a7-aba4-4ac7-acad-0895e798b8de",
  "pair":           "EURUSD",
  "strategy_name":  "rsi",
  "start_date":     "2021-01-01",
  "end_date":       "2023-12-29",
  "data_source":    "csv"
}'
# Expected: HTTP 200 — confirms old endpoint untouched
=============================================================
"""

if __name__ == "__main__":
    print(CURL_COMMANDS)
    asyncio.run(run_integration_test())
