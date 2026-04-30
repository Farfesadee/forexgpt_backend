"""
services/backtest_service.py
Backtest pipeline service.

Flow:
    1. Create a pending backtest row         — db.backtests.create()
    2. Fetch price data                      — DataFetcher
    3. Run engine                            — BacktestEngine
    4. Calculate metrics                     — PerformanceMetrics
    5. Save results + trades                 — db.backtests.save_results()
                                               db.backtests.save_trades()
    6. Increment profile counter             — db.profiles.increment_counter()

The sync_backtest_on_complete DB trigger fires on save_results() and
automatically denormalizes sharpe_ratio, total_return_pct, max_drawdown_pct,
win_rate_pct, total_trades into the backtests row for fast list queries.

Error handling:
    Any failure after create() calls db.backtests.set_status("failed")
    so the row is never left in "pending" state.
"""
import json
import numpy as np
import pandas as pd
import logging
import ast
import textwrap
import re
import subprocess
import tempfile
import os
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from core.database import db

from backtesting.data_fetcher import DataFetcher
from backtesting.engine.backtest_engine import BacktestEngine
from backtesting.costs.cost_model import get_cost_model
from backtesting.metrics.performance_metrics import PerformanceMetrics

logger = logging.getLogger(__name__)


class BacktestExecutionTimeoutError(RuntimeError):
    """Raised when sandboxed custom strategy execution exceeds the time limit."""


_CODE_LINE_RE = re.compile(
    r"^\s*(from\s+\w+\s+import|import\s+\w+|def\s+\w+|class\s+\w+|@|#|[A-Za-z_]\w*\s*=)"
)


def _is_parseable_python(text: str) -> bool:
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


def _extract_parseable_code(text: str) -> str:
    """
    Recover the real Python block from mixed AI output.

    Handles cases where the payload accidentally includes prose before/after
    the strategy code even though the caller expected pure Python.
    """
    lines = text.splitlines()
    candidate_starts = [0]
    candidate_starts.extend(
        idx for idx, line in enumerate(lines) if _CODE_LINE_RE.match(line)
    )

    seen: set[int] = set()
    for start_idx in candidate_starts:
        if start_idx in seen:
            continue
        seen.add(start_idx)

        candidate = textwrap.dedent("\n".join(lines[start_idx:])).strip()
        if not candidate or "def generate_signals" not in candidate:
            continue

        if _is_parseable_python(candidate):
            return candidate

        candidate_lines = candidate.splitlines()
        for end_idx in range(len(candidate_lines) - 1, 0, -1):
            trimmed = "\n".join(candidate_lines[:end_idx]).strip()
            if "def generate_signals" not in trimmed:
                continue
            if _is_parseable_python(trimmed):
                return trimmed

    return text


def _normalize_custom_code(code: str) -> str:
    """Strip markdown fences and leading indentation from generated code."""
    text = (code or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    if "```python" in text:
        start = text.find("```python") + len("```python")
        end = text.find("```", start)
        if end != -1:
            text = text[start:end]
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end != -1:
            text = text[start:end]

    text = textwrap.dedent(text).strip()
    
    # ── Extract parseable code only as fallback for mixed AI output ────────
    # Note: _extract_parseable_code may trim lines to make code parseable,
    # so it should only be used if the stripped markdown code doesn't work.
    # Try parsing the stripped code first before attempting extraction.
    try:
        ast.parse(text)
        # Code is parseable as-is, return it
        return text
    except SyntaxError:
        # Code has syntax errors, try extracting from mixed content
        # This will attempt to find the longest parseable block
        return _extract_parseable_code(text).strip()


# ============================================================================
# STRATEGY BUILDER
# Returns a callable compatible with BacktestEngine.run_backtest()
# ============================================================================

import math

def _make_serializable(obj):
    """Convert pandas/numpy types to JSON-serializable Python types."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(i) for i in obj]
    elif hasattr(obj, 'isoformat'):  # datetime, Timestamp
        return obj.isoformat()
    elif isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, (np.floating, float)):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    elif isinstance(obj, np.ndarray):
        return [_make_serializable(i) for i in obj.tolist()]
    return obj


def _first_param(params: Dict[str, Any], *names: str, default: Any = None) -> Any:
    """Return the first non-empty parameter value from a list of aliases."""
    for name in names:
        if name in params and params[name] is not None:
            return params[name]
    return default


# ============================================================================
# STRATEGY BUILDER
# Returns a callable compatible with BacktestEngine.run_backtest()
#
# CHANGE FROM PREVIOUS VERSION:
#   Every strategy fn() now returns a TUPLE (signal, reason) instead of a
#   plain string. The reason is a human-readable explanation of why the
#   signal fired — e.g. "RSI = 28.4 < 30 (oversold)".
#   BacktestEngine.run_backtest() handles both tuple and plain-string returns
#   transparently for backwards compatibility.
# ============================================================================


def _build_strategy(strategy: str, params: Dict[str, Any]):
    """Build a strategy function from name + params."""
    strategy = strategy.lower().replace(" ", "_")

    # Accept the common shorthand used by the frontend/test prompts.
    if strategy in {"sma", "sma_cross", "sma_crossover"}:
        strategy = "moving_average_crossover"
    if strategy == "sma_cross":
        strategy = "moving_average_crossover"
    if strategy == "ma_cross":
        strategy = "moving_average_crossover"
    if strategy == "bollinger":
        strategy = "bollinger_bands"

    # -------------------------------------------------------------------------
    # RSI — Relative Strength Index
    # -------------------------------------------------------------------------

    if strategy == "rsi":
        period = int(_first_param(params, "period", "rsi_period", default=14))
        oversold = float(_first_param(
            params,
            "oversold",
            "lower_threshold",
            "buy_threshold",
            default=30,
        ))
        overbought = float(_first_param(
            params,
            "overbought",
            "upper_threshold",
            "sell_threshold",
            default=70,
        ))

        def fn(data):
            if len(data) < period + 1:
                return None, None
            close = data["close"]
            delta = close.diff()
            gain  = delta.where(delta > 0, 0.0).rolling(period).mean()
            loss  = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
            rsi   = 100 - (100 / (1 + gain / loss))
            current_rsi = round(float(rsi.iloc[-1]), 2)
            
            if rsi.iloc[-1] < oversold  and rsi.iloc[-2] >= oversold:
                return "buy", f"BUY - RSI = {current_rsi} dropped below {oversold} (oversold signal)"
            if rsi.iloc[-1] > overbought and rsi.iloc[-2] <= overbought:
                return "sell", f"SELL - RSI = {current_rsi} rose above {overbought} (overbought signal)"
            return None, None
        
        return fn

    # -------------------------------------------------------------------------
    # Moving Average Crossover
    # -------------------------------------------------------------------------
    
    elif strategy == "moving_average_crossover":
        fast = int(_first_param(
            params,
            "fast_period",
            "fast",
            "short_period",
            "fast_window",
            default=10,
        ))
        slow = int(_first_param(
            params,
            "slow_period",
            "slow",
            "long_period",
            "slow_window",
            default=30,
        ))

        def fn(data):
            required_bars = max(fast, slow) + 1
            if len(data) < required_bars:
                return None, None
            close   = data["close"]
            fast_ma = close.rolling(fast).mean()
            slow_ma = close.rolling(slow).mean()
            current_fast = round(float(fast_ma.iloc[-1]), 5)
            current_slow = round(float(slow_ma.iloc[-1]), 5)

            if fast_ma.iloc[-1] > slow_ma.iloc[-1] and fast_ma.iloc[-2] <= slow_ma.iloc[-2]:
                return ("buy", f"BUY - MA{fast} ({current_fast}) crossed above MA{slow} ({current_slow}) - bullish crossover")
            if fast_ma.iloc[-1] < slow_ma.iloc[-1] and fast_ma.iloc[-2] >= slow_ma.iloc[-2]:
                return ("sell", f"SELL - MA{fast} ({current_fast}) crossed below MA{slow} ({current_slow}) - bearish crossover")
            return None, None
        
        return fn

    # -------------------------------------------------------------------------
    # Bollinger Bands
    # -------------------------------------------------------------------------
    
    elif strategy == "bollinger_bands":
        period  = params.get("period", 20)
        std_dev = params.get("std_dev", 2.0)

        def fn(data):
            if len(data) < period:
                return None, None
            close  = data["close"]
            middle = close.rolling(period).mean()
            std    = close.rolling(period).std()
            upper  = (middle + std_dev * std).iloc[-1]
            lower  = (middle - std_dev * std).iloc[-1]
            price  = close.iloc[-1]
            current_price = round(float(price), 5)
            current_upper = round(float(upper), 5)
            current_lower = round(float(lower), 5)
            
            if price <= lower:
                return ("buy", f"BUY - Price ({current_price}) touched lower band ({current_lower}) - oversold signal")
            if price >= upper:
                return ("sell", f"SELL - Price ({current_price}) touched upper band ({current_upper}) - overbought signal")
            return None, None
        
        return fn

    # -------------------------------------------------------------------------
    # MACD — Moving Average Convergence Divergence
    # -------------------------------------------------------------------------
    
    elif strategy == "macd":
        fast   = params.get("fast", 12)
        slow   = params.get("slow", 26)
        signal = params.get("signal", 9)

        def fn(data):
            if len(data) < slow:
                return None, None
            close    = data["close"]
            ema_fast = close.ewm(span=fast,   adjust=False).mean()
            ema_slow = close.ewm(span=slow,   adjust=False).mean()
            macd     = ema_fast - ema_slow
            sig_line = macd.ewm(span=signal,  adjust=False).mean()
            current_macd   = round(float(macd.iloc[-1]),     6)
            current_signal = round(float(sig_line.iloc[-1]), 6)
            
            if macd.iloc[-1] > sig_line.iloc[-1] and macd.iloc[-2] <= sig_line.iloc[-2]:
                return ("buy", f"BUY - MACD ({current_macd}) crossed above signal line ({current_signal}) - bullish momentum")
            if macd.iloc[-1] < sig_line.iloc[-1] and macd.iloc[-2] >= sig_line.iloc[-2]:
                return ("sell", f"SELL - MACD ({current_macd}) crossed below signal line ({current_signal}) - bearish momentum")
            return None, None
        
        return fn

    else:
        raise ValueError(
            f"Unknown strategy '{strategy}'. "
            f"Supported: rsi, sma, sma_cross, moving_average_crossover, bollinger, bollinger_bands, macd"
        )


# ============================================================================
# SERVICE
# ============================================================================

class BacktestService:
    """
    Backtest service — uses db.backtests (BacktestsRepo) from core/database.py.
    No direct Supabase client needed — all DB access goes through the repo.
    """

    # -------------------------------------------------------------------------
    # RUN
    # -------------------------------------------------------------------------

    async def run_backtest(
        self,
        user_id:           str,
        strategy_id:       Optional[str],
        pair:              str,
        start_date:        str,
        end_date:          str,
        timeframe:         str = "1d",
        initial_capital:   float = 10000.0,
        strategy_name:     str = "rsi",
        strategy_params:   Optional[Dict[str, Any]] = None,
        cost_preset:       str = "forex_retail",
        position_size_pct: float = 0.1,
        data_source:       str = "auto",
    ) -> Dict[str, Any]:
        """
        Full parameterized backtest pipeline.

        Args:
            user_id:           Supabase auth user UUID
            strategy_id:       Optional FK to strategies table
            pair:              Currency pair e.g. "EURUSD"
            start_date:        "YYYY-MM-DD"
            end_date:          "YYYY-MM-DD"
            timeframe:         "1d" or "1wk"
            initial_capital:   Starting capital
            strategy_name:     rsi | sma | moving_average_crossover | bollinger | bollinger_bands | macd
            strategy_params:   Strategy-specific parameters
            cost_preset:       From CostModel presets
            position_size_pct: Fraction of capital per trade
            data_source:       auto | yfinance | alphavantage | csv

        Returns:
            The completed backtest row dict from Supabase
        """
        strategy_params = strategy_params or {}
        pair            = pair.upper()

        logger.info(f"Backtest: {strategy_name} on {pair} [{start_date} -> {end_date}] user={user_id}")

        # ── Step 1: Create pending row ────────────────────────────────────────
        # This gives us a backtest_id immediately so we can update status
        # if anything fails downstream
        # REPLACE WITH:
        record = db.backtests.create(user_id, {
            "strategy_id":     strategy_id,
            "pair":            pair,
            "start_date":      start_date,
            "end_date":        end_date,
            "timeframe":       timeframe,
            "initial_capital": initial_capital,
            "strategy_name":   strategy_name,
            "strategy_config": {
                "strategy_params":   strategy_params,
                "cost_preset":       cost_preset,
                "position_size_pct": position_size_pct,
                "data_source":       data_source
            }
        })
        backtest_id = record["id"]
        logger.info(f"Created pending backtest {backtest_id}")

        try:
            # ── Step 2: Fetch price data ──────────────────────────────────────
            fetcher = DataFetcher()
            df      = fetcher.fetch(pair, start_date, end_date,
                                    interval=timeframe, source=data_source)

            data = df.reset_index()
            col  = "Date" if "Date" in data.columns else data.columns[0]
            data = data.rename(columns={col: "date"})

            # ── Step 3: Build strategy + run engine ───────────────────────────
            strategy_fn = _build_strategy(strategy_name, strategy_params)
            cost_model  = get_cost_model(cost_preset)
            engine      = BacktestEngine(
                initial_capital=initial_capital,
                cost_model=cost_model,
                position_size_pct=position_size_pct
            )
            raw_results = engine.run_backtest(data, strategy_fn)

            # ── Step 4: Calculate metrics ─────────────────────────────────────
            metrics = PerformanceMetrics(raw_results).calculate_all_metrics()

            # ── Step 5: Save results + trades ─────────────────────────────────
            # save_results() triggers sync_backtest_on_complete in the DB
            # which denormalizes sharpe_ratio, total_return_pct etc.
            db.backtests.save_results(backtest_id, {
                "metrics":      _make_serializable(metrics),
                "equity_curve": _make_serializable(raw_results.get("equity_curve", [])),
            })

            # Save individual trades to backtest_trades table
            trades = raw_results.get("trades", [])
            if trades:
                db.backtests.save_trades(backtest_id, user_id, _make_serializable(trades))

            # ── Step 6: Increment profile counter ───────────────────────────
            try:
                db.profiles.increment_counter(user_id, "backtests")
            except Exception as e:
                logger.warning(f"Could not increment profile counter: {e}")
                # Non-critical — don't fail the backtest over this
            logger.info(
                f"Backtest {backtest_id} completed: "
                f"{metrics['total_trades']} trades, "
                f"{metrics['total_return_pct']}% return"
            )

            # Return the full completed row
            return db.backtests.get(backtest_id)

        except Exception as e:
            # Mark as failed so it's never left as "pending"
            logger.error(f"Backtest {backtest_id} failed: {e}")
            db.backtests.set_status(backtest_id, "failed", error=str(e))
            raise

    # -------------------------------------------------------------------------
    # LIST
    # -------------------------------------------------------------------------

    async def get_user_backtests(
        self,
        user_id: str,
        pair:    Optional[str] = None,
        limit:   int = 100
    ) -> List[Dict]:
        """List completed backtests for a user, newest first."""
        return db.backtests.list(user_id, pair=pair, limit=limit)

    # -------------------------------------------------------------------------
    # GET ONE
    # -------------------------------------------------------------------------

    async def get_backtest_by_id(
        self, backtest_id: str, user_id: str
    ) -> Optional[Dict]:
        """Get full backtest detail. Returns None if not found or wrong user."""
        try:
            record = db.backtests.get(backtest_id)
            # Verify ownership — repo returns the row regardless of user
            if record and record.get("user_id") != user_id:
                return None
            return record
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # GET TRADES
    # -------------------------------------------------------------------------

    async def get_backtest_trades(
        self,
        backtest_id: str,
        user_id:     str,
        limit:       int = 500,
        offset:      int = 0
    ) -> List[Dict]:
        """Get individual trades for a backtest."""
        # Ownership check first
        record = await self.get_backtest_by_id(backtest_id, user_id)
        if record is None:
            return []
        return db.backtests.get_trades(backtest_id, limit=limit, offset=offset)

    # -------------------------------------------------------------------------
    # DELETE
    # -------------------------------------------------------------------------

    async def delete_backtest(
        self, backtest_id: str, user_id: str
    ) -> bool:
        """Delete a backtest. Returns True if deleted, False if not found."""
        record = await self.get_backtest_by_id(backtest_id, user_id)
        if record is None:
            return False
        # BacktestsRepo doesn't have a delete method — add direct call
        from core.database import get_db
        get_db().table("backtests").delete().eq("id", backtest_id).execute()
        return True
    
    
    # =========================================================================
    # CUSTOM STRATEGY — PRIVATE HELPERS
    # =========================================================================

    def _validate_code_safety(self, code: str) -> None:
        """
        Security gate for user-submitted strategy code.

        Checks for dangerous operations and enforces the
        generate_signals(data) contract.

        Raises:
            ValueError: if code is unsafe or missing the required function.
        """
        FORBIDDEN = [
            "os.system",   "subprocess",  "eval(",    "exec(",
            "__import__",  "open(",       "file(",    "input(",
            "requests.",   "urllib.",     "socket.",  "sys.exit",
            "compile(",    "globals(",    "locals(",  "vars(",
            "shutil.",     "pathlib.",    "importlib",
        ]

        code_lower = code.lower()
        for token in FORBIDDEN:
            if token.lower() in code_lower:
                raise ValueError(
                    f"Code contains a forbidden operation: '{token}'. "
                    f"Only pandas and numpy are allowed."
                )

        if "def generate_signals" not in code:
            raise ValueError(
                "Code must define a 'generate_signals(data)' function. "
                "It receives a pandas DataFrame and must return a list or "
                "Series of signals: 1 = BUY, -1 = SELL, 0 = HOLD."
            )

        if len(code) > 10_000:
            raise ValueError(
                "Code exceeds the 10 KB size limit. Please simplify your strategy."
            )

    # -------------------------------------------------------------------------

    async def _execute_strategy_code(
        self,
        code: str,
        data,           # pd.DataFrame with lowercase columns incl. 'close'
    ):
        """
        Execute user strategy code in an isolated subprocess.

        The subprocess receives price data via a temp JSON file,
        runs generate_signals(data), and prints the signals as JSON.
        A 30-second timeout kills runaway code.

        Returns:
            pd.Series of signals (1 / -1 / 0), same length as data.

        Raises:
            ValueError: strategy execution error (shown to user).
            Exception:  timeout or output parsing failure.
        """
        import subprocess
        import tempfile
        import os
        import pandas as pd

        data_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        code_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )

        try:
            # ── Write price data to temp JSON ─────────────────────────────────
            data.to_json(data_file.name, orient="records", date_format="iso")
            data_file.close()

            data_file_path = data_file.name.replace("\\", "/")
            
            # ── Build the wrapper that loads data + calls user code ───────────
            # Double-braces {{ }} are Python f-string escapes for literal { }
            wrapper = f"""
import pandas as pd
import numpy as np
import json, sys
from typing import *

# Load price data
with open('{data_file_path}', 'r') as f:
    records = json.load(f)

data = pd.DataFrame(records)
if 'date' in data.columns:
    data['date'] = pd.to_datetime(data['date'])
    data = data.set_index('date')

# ── User strategy code ────────────────────────────────────────────
{code}
# ─────────────────────────────────────────────────────────────────

try:
    signals = generate_signals(data)

    if isinstance(signals, pd.Series):
        result = signals.fillna(0).astype(int).tolist()
    elif isinstance(signals, (list, tuple)):
        result = [int(s) for s in signals]
    else:
        result = list(signals)

    print(json.dumps({{"signals": result, "success": True}}))

except Exception as e:
    print(json.dumps({{"error": str(e), "success": False}}))
    sys.exit(1)
"""
            code_file.write(wrapper)
            code_file.close()

            # ── Run in subprocess with hard 40-second timeout ─────────────────
            result = subprocess.run(
                ["python", code_file.name],
                capture_output=True,
                text=True,
                timeout=40,
            )

           
            if result.returncode != 0:
                # Try stdout first (strategy runtime errors land here as JSON)
                # Fall back to stderr (syntax errors and subprocess failures)
                try:
                    output = json.loads(result.stdout)
                    if not output.get("success"):
                        raise ValueError(f"Strategy error: {output.get('error', 'unknown error')}")
                except (json.JSONDecodeError, KeyError):
                    err = result.stderr.strip().splitlines()
                    raise ValueError(
                        f"Strategy execution failed: {err[-1] if err else result.stderr}"
                    )

            # Parse output
            try:
                output = json.loads(result.stdout)
            except json.JSONDecodeError:

                if not output.get("success"):
                    raise ValueError(f"Strategy error: {output.get('error')}")

            signals_series = pd.Series(output["signals"], dtype=float)

            # Align length — pad/trim to match price data length
            n = len(data)
            if len(signals_series) < n:
                signals_series = signals_series.reindex(range(n), fill_value=0)
            elif len(signals_series) > n:
                signals_series = signals_series.iloc[:n]

            return signals_series

        except subprocess.TimeoutExpired:
            raise BacktestExecutionTimeoutError(
                "Strategy execution timed out (40 s limit). "
                "Simplify your logic or reduce the date range."
            )

        finally:
            # Always clean up temp files
            for path in (data_file.name, code_file.name):
                try:
                    os.unlink(path)
                except Exception:
                    pass

    # -------------------------------------------------------------------------

    async def run_custom_strategy(
        self,
        user_id:           str,
        custom_code:       str,
        pair:              str,
        start_date:        str,
        end_date:          str,
        timeframe:         str = "1d",
        initial_capital:   float = 10000.0,
        position_size_pct: float = 0.1,
        data_source:       str = "auto",
    ) -> Dict[str, Any]:
        """
        Run a backtest using user-provided Python code.
        """
        pair = pair.upper()
        logger.info(f"Custom Backtest: {pair} [{start_date} -> {end_date}] user={user_id}")

        # ── Step 1: Validate code safety ──────────────────────────────────────
        # Raises ValueError immediately — no DB row created yet
        self._validate_code_safety(custom_code)
        
        # # Only normalize AFTER validation passes
        # custom_code = _normalize_custom_code(custom_code)

        # 2. Create pending row
        record = db.backtests.create(user_id, {
            "strategy_id":     None,
            "pair":            pair,
            "start_date":      start_date,
            "end_date":        end_date,
            "timeframe":       timeframe,
            "initial_capital": initial_capital,
            "strategy_name":   "custom",
            "strategy_config": {
                "strategy_params":   {},
                "cost_preset":       "forex_retail",
                "position_size_pct": position_size_pct,
                "data_source":       data_source,
                "custom_code":       custom_code
            }
        })
        backtest_id = record["id"]

        try:
            # 3. Fetch data
            fetcher = DataFetcher()
            df = fetcher.fetch(pair, start_date, end_date, interval=timeframe, source=data_source)
            
            data = df.reset_index()
            col = "Date" if "Date" in data.columns else data.columns[0]
            data = data.rename(columns={col: "date"})

            # 4. Execute custom strategy code to get signals
            signals = await self._execute_strategy_code(custom_code, data)

            # ── Step 5: Build PerformanceMetrics-compatible dict ──────────────
            results_dict = self._build_custom_results_dict(
                data, signals, initial_capital
            )

            # ── Step 6: Calculate metrics (reuses PerformanceMetrics) ─────────
            metrics = PerformanceMetrics(results_dict).calculate_all_metrics()

            # 7. Save results
            db.backtests.save_results(backtest_id, {
                "metrics":      _make_serializable(metrics),
                "equity_curve": _make_serializable(raw_results.get("equity_curve", [])),
            })

            if raw_results.get("trades"):
                db.backtests.save_trades(backtest_id, user_id, _make_serializable(raw_results["trades"]))

            # 8. Increment profile counter
            try:
                db.profiles.increment_counter(user_id, "backtests")
            except Exception as e:
                logger.warning(f"Could not increment profile counter: {e}")

            return db.backtests.get(backtest_id)

        except Exception as e:
            logger.error(f"Custom backtest {backtest_id} failed: {e}")
            db.backtests.set_status(backtest_id, "failed", error=str(e))
            raise

    def _validate_code_safety(self, code: str):
        """
        Basic static analysis to prevent dangerous code execution.
        """
        if len(code) > 10000:
            raise ValueError("Strategy code too large (max 10 KB).")

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise ValueError(f"Syntax error in strategy code: {e}")

        # Check for required function
        has_func = any(
            isinstance(node, ast.FunctionDef) and node.name == "generate_signals"
            for node in tree.body
        )
        if not has_func:
            raise ValueError("Code must define a 'generate_signals(data)' function.")

        # Forbidden keywords and modules
        forbidden = {
            "os", "subprocess", "sys", "shutil", "requests", "httpx", "socket",
            "eval", "exec", "open", "__import__", "getattr", "setattr", "delattr",
            "pickle", "marshal", "builtins", "__builtin__", "globals", "locals"
        }

        for node in ast.walk(tree):
            # Check for imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split('.')[0] in forbidden:
                        raise ValueError(f"Import of module '{alias.name}' is forbidden.")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split('.')[0] in forbidden:
                    raise ValueError(f"Import from module '{node.module}' is forbidden.")
            
            # Check for function calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in forbidden:
                        raise ValueError(f"Call to function '{node.func.id}' is forbidden.")
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in forbidden:
                        raise ValueError(f"Access to attribute '{node.func.attr}' is forbidden.")

    async def _execute_strategy_code(self, code: str, data: pd.DataFrame) -> pd.Series:
        """
        Executes user code in a restricted environment and returns signals.
        """
        # Prepare restricted globals
        restricted_globals = {
            "pd": pd,
            "np": np,
            "__builtins__": {
                "__import__": __import__,  # Needed for 'import' statements to work
                "range": range, "len": len, "list": list, "dict": dict, "set": set,
                "int": int, "float": float, "str": str, "bool": bool, "round": round,
                "min": min, "max": max, "sum": sum, "abs": abs, "enumerate": enumerate,
                "zip": zip, "any": any, "all": all, "sorted": sorted, "reversed": reversed,
                "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
                "RuntimeError": RuntimeError
            }
        }
        
        try:
            # Execute the code to define the functions in restricted_globals
            exec(code, restricted_globals)
            
            if "generate_signals" not in restricted_globals:
                raise ValueError("generate_signals function not found after execution.")
            
            # Call the function
            signals = restricted_globals["generate_signals"](data)
            
            # Convert to pandas series
            if not isinstance(signals, (list, np.ndarray, pd.Series)):
                raise ValueError("generate_signals must return a list, numpy array, or pandas Series.")
            
            sig_series = pd.Series(signals)
            if len(sig_series) != len(data):
                raise ValueError(f"Signal length ({len(sig_series)}) does not match data length ({len(data)}).")
            
            return sig_series

        except Exception as e:
            logger.error(f"Error executing custom strategy: {e}")
            raise ValueError(f"Strategy runtime error: {e}")
