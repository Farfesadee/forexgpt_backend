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
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from core.database import db

from backtesting.data_fetcher import DataFetcher
from backtesting.engine.backtest_engine import BacktestEngine
from backtesting.costs.cost_model import get_cost_model
from backtesting.metrics.performance_metrics import PerformanceMetrics

logger = logging.getLogger(__name__)


# ============================================================================
# STRATEGY BUILDER
# Returns a callable compatible with BacktestEngine.run_backtest()
# ============================================================================

def _make_serializable(obj):
    """Convert pandas/numpy types to JSON-serializable Python types."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(i) for i in obj]
    elif hasattr(obj, 'isoformat'):  # datetime, Timestamp
        return obj.isoformat()
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

def _build_strategy(strategy: str, params: Dict[str, Any]):
    """Build a strategy function from name + params."""
    strategy = strategy.lower().replace(" ", "_")

    # Accept the common shorthand used by the frontend/test prompts.
    if strategy == "sma":
        strategy = "moving_average_crossover"
    if strategy == "bollinger":
        strategy = "bollinger_bands"

    if strategy == "rsi":
        period     = params.get("period", 14)
        oversold   = params.get("oversold", 30)
        overbought = params.get("overbought", 70)

        def fn(data):
            if len(data) < period + 1:
                return None
            close = data["close"]
            delta = close.diff()
            gain  = delta.where(delta > 0, 0.0).rolling(period).mean()
            loss  = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
            rsi   = 100 - (100 / (1 + gain / loss))
            if rsi.iloc[-1] < oversold  and rsi.iloc[-2] >= oversold:
                return "buy"
            if rsi.iloc[-1] > overbought and rsi.iloc[-2] <= overbought:
                return "sell"
            return None
        return fn

    elif strategy == "moving_average_crossover":
        fast = params.get("fast_period", 50)
        slow = params.get("slow_period", 200)

        def fn(data):
            if len(data) < slow:
                return None
            close   = data["close"]
            fast_ma = close.rolling(fast).mean()
            slow_ma = close.rolling(slow).mean()
            if fast_ma.iloc[-1] > slow_ma.iloc[-1] and fast_ma.iloc[-2] <= slow_ma.iloc[-2]:
                return "buy"
            if fast_ma.iloc[-1] < slow_ma.iloc[-1] and fast_ma.iloc[-2] >= slow_ma.iloc[-2]:
                return "sell"
            return None
        return fn

    elif strategy == "bollinger_bands":
        period  = params.get("period", 20)
        std_dev = params.get("std_dev", 2.0)

        def fn(data):
            if len(data) < period:
                return None
            close  = data["close"]
            middle = close.rolling(period).mean()
            std    = close.rolling(period).std()
            upper  = (middle + std_dev * std).iloc[-1]
            lower  = (middle - std_dev * std).iloc[-1]
            price  = close.iloc[-1]
            if price <= lower:
                return "buy"
            if price >= upper:
                return "sell"
            return None
        return fn

    elif strategy == "macd":
        fast   = params.get("fast", 12)
        slow   = params.get("slow", 26)
        signal = params.get("signal", 9)

        def fn(data):
            if len(data) < slow:
                return None
            close    = data["close"]
            ema_fast = close.ewm(span=fast,   adjust=False).mean()
            ema_slow = close.ewm(span=slow,   adjust=False).mean()
            macd     = ema_fast - ema_slow
            sig_line = macd.ewm(span=signal,  adjust=False).mean()
            if macd.iloc[-1] > sig_line.iloc[-1] and macd.iloc[-2] <= sig_line.iloc[-2]:
                return "buy"
            if macd.iloc[-1] < sig_line.iloc[-1] and macd.iloc[-2] >= sig_line.iloc[-2]:
                return "sell"
            return None
        return fn

    else:
        raise ValueError(
            f"Unknown strategy '{strategy}'. "
            f"Supported: rsi, sma, moving_average_crossover, bollinger, bollinger_bands, macd"
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
        Full backtest pipeline.

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
        limit:   int = 20
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

            # ── Run in subprocess with hard 30-second timeout ─────────────────
            result = subprocess.run(
                ["python", code_file.name],
                capture_output=True,
                text=True,
                timeout=30,
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
            raise Exception(
                "Strategy execution timed out (30 s limit). "
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

    def _build_custom_results_dict(
        self,
        data,               # pd.DataFrame — price data with 'close' column
        signals,            # pd.Series — 1/−1/0 per row
        initial_capital: float,
    ) -> dict:
        """
        Adapter: converts raw signals + price data into the dict shape
        that PerformanceMetrics expects, so we reuse all existing metric
        calculations without duplication.

        PerformanceMetrics needs:
            initial_capital, final_capital,
            trades: [{net_pnl, gross_pnl, holding_days, entry_date,
                      exit_date, entry_price, exit_price, side,
                      spread_cost, slippage_cost, commission,
                      financing_cost, exchange_fees, total_cost}]
            equity_curve: [{date, total_equity}]

        Custom strategies have no cost model, so all cost fields are 0.
        This is intentional — the user wrote the code, cost modelling
        is the domain of the parameterised path.
        """
        import pandas as pd
        import numpy as np

        close     = data["close"].reset_index(drop=True)
        sig       = signals.reset_index(drop=True).fillna(0).astype(int)

        # ── Build trade list ──────────────────────────────────────────────────
        trades       = []
        position     = 0        # 0 = flat, 1 = long, -1 = short
        entry_price  = 0.0
        entry_idx    = 0

        # Derive date index — handle both DatetimeIndex and integer index
        if hasattr(data.index, "to_pydatetime"):
            dates = list(data.index)
        elif "date" in data.columns:
            dates = list(pd.to_datetime(data["date"]))
        else:
            dates = list(range(len(data)))

        for i in range(len(sig)):
            signal = int(sig.iloc[i])

            if position == 0 and signal in (1, -1):
                # Open position
                position    = signal
                entry_price = float(close.iloc[i])
                entry_idx   = i

            elif position != 0 and (signal == -position or signal == 0):
                # Close position
                exit_price   = float(close.iloc[i])
                holding_days = i - entry_idx
                gross_pnl    = (exit_price - entry_price) * position
                net_pnl      = gross_pnl   # no costs on custom path

                trades.append({
                    "entry_date":     dates[entry_idx],
                    "exit_date":      dates[i],
                    "entry_price":    round(entry_price, 5),
                    "exit_price":     round(exit_price, 5),
                    "side":           "buy" if position == 1 else "sell",
                    "holding_days":   holding_days,
                    "gross_pnl":      round(gross_pnl, 6),
                    "net_pnl":        round(net_pnl, 6),
                    "return_pct":     round((gross_pnl / entry_price) * 100, 4),
                    "quantity":       1.0,
                    # Cost fields — zero for custom strategies
                    "spread_cost":    0.0,
                    "slippage_cost":  0.0,
                    "commission":     0.0,
                    "financing_cost": 0.0,
                    "exchange_fees":  0.0,
                    "total_cost":     0.0,
                })
                position = 0

                # Immediately re-open if new signal is opposite direction
                if signal in (1, -1):
                    position    = signal
                    entry_price = float(close.iloc[i])
                    entry_idx   = i

        # ── Build equity curve ────────────────────────────────────────────────
        # Simple daily mark-to-market: start at initial_capital,
        # apply daily pct change only when in a position.
        equity      = initial_capital
        equity_curve = []
        pos_running  = 0

        for i in range(len(close)):
            signal = int(sig.iloc[i])

            if pos_running == 0 and signal in (1, -1):
                pos_running = signal
            elif pos_running != 0 and signal == 0:
                pos_running = 0

            if i > 0 and pos_running != 0:
                daily_ret = (float(close.iloc[i]) - float(close.iloc[i - 1])) / float(close.iloc[i - 1])
                equity   *= (1 + daily_ret * pos_running)

            equity_curve.append({
                "date":         dates[i],
                "total_equity": round(equity, 4),
            })

        final_capital = equity_curve[-1]["total_equity"] if equity_curve else initial_capital

        return {
            "initial_capital": initial_capital,
            "final_capital":   final_capital,
            "trades":          trades,
            "equity_curve":    equity_curve,
        }

    # =========================================================================
    # CUSTOM STRATEGY — PUBLIC METHOD
    # =========================================================================

    async def run_custom_strategy(
        self,
        user_id:           str,
        custom_code:       str,
        pair:              str,
        start_date:        str,
        end_date:          str,
        timeframe:         str   = "1d",
        initial_capital:   float = 10000.0,
        position_size_pct: float = 0.1,
        data_source:       str   = "csv",
    ) -> Dict[str, Any]:
        """
        Execute a user-generated strategy and return full backtest results.

        Flow:
            1. Validate code safety
            2. Create pending DB row
            3. Fetch price data (reuses existing DataFetcher)
            4. Execute code in sandbox subprocess
            5. Build PerformanceMetrics-compatible results dict
            6. Calculate metrics via PerformanceMetrics (same as parameterised)
            7. Save results to backtests table (same repo, strategy_name='custom')
            8. Save trades to backtest_trades table
            9. Increment profile counter
           10. Return completed row

        Args:
            user_id:           Supabase auth user UUID
            custom_code:       Python code containing generate_signals(data)
            pair:              Currency pair e.g. "EURUSD"
            start_date:        "YYYY-MM-DD"
            end_date:          "YYYY-MM-DD"
            timeframe:         "1d" | "1wk"
            initial_capital:   Starting capital in USD
            position_size_pct: Not used in cost calc but stored for reference
            data_source:       "csv" recommended (yfinance unreliable for forex)

        Returns:
            The completed backtests row dict from Supabase
            (identical shape to run_backtest() — same table, same fields)
        """
        pair = pair.upper()

        # ── Step 1: Validate code safety ──────────────────────────────────────
        # Raises ValueError immediately — no DB row created yet
        self._validate_code_safety(custom_code)

        logger.info(
            f"Custom backtest: {pair} [{start_date} -> {end_date}] user={user_id}"
        )

        # ── Step 2: Create pending DB row ─────────────────────────────────────
        # strategy_name = "custom" so it appears correctly in history list
        # custom_code stored in strategy_config for the improve-loop
        record = db.backtests.create(user_id, {
            "pair":            pair,
            "start_date":      start_date,
            "end_date":        end_date,
            "timeframe":       timeframe,
            "initial_capital": initial_capital,
            "strategy_name":   "custom",
            "strategy_id":     None,
            "strategy_config": {
                "strategy_params":  {},            # no predefined params for custom code
                "cost_preset":      "none",
                "position_size_pct": position_size_pct,
                "data_source":       data_source,
                "custom_code":       custom_code,   # stored for CodeGen improve-loop
            },
        })
        backtest_id = record["id"]
        logger.info(f"Created pending custom backtest {backtest_id}")

        try:
            # ── Step 3: Fetch price data ──────────────────────────────────────
            # Reuses existing DataFetcher — same as parameterised path
            fetcher = DataFetcher()
            df      = fetcher.fetch(
                pair, start_date, end_date,
                interval=timeframe, source=data_source
            )

            data = df.reset_index()
            col  = "Date" if "Date" in data.columns else data.columns[0]
            data = data.rename(columns={col: "date"})

            if data.empty:
                raise ValueError(
                    f"No price data available for {pair} "
                    f"from {start_date} to {end_date}."
                )

            # ── Step 4: Execute strategy in sandbox ───────────────────────────
            signals = await self._execute_strategy_code(custom_code, data)

            # ── Step 5: Build PerformanceMetrics-compatible dict ──────────────
            results_dict = self._build_custom_results_dict(
                data, signals, initial_capital
            )

            # ── Step 6: Calculate metrics (reuses PerformanceMetrics) ─────────
            metrics = PerformanceMetrics(results_dict).calculate_all_metrics()

            # ── Step 7: Save results (triggers DB denormalization trigger) ─────
            db.backtests.save_results(backtest_id, {
                "metrics":      _make_serializable(metrics),
                "equity_curve": _make_serializable(
                    results_dict.get("equity_curve", [])
                ),
            })

            # ── Step 8: Save trades ───────────────────────────────────────────
            trades = results_dict.get("trades", [])
            if trades:
                db.backtests.save_trades(
                    backtest_id, user_id, _make_serializable(trades)
                )

            # ── Step 9: Increment profile counter (non-critical) ──────────────
            try:
                db.profiles.increment_counter(user_id, "backtests")
            except Exception as e:
                logger.warning(f"Could not increment profile counter: {e}")

            logger.info(
                f"Custom backtest {backtest_id} completed: "
                f"{metrics['total_trades']} trades, "
                f"{metrics['total_return_pct']}% return"
            )

            # ── Step 10: Return completed row (same shape as run_backtest) ─────
            return db.backtests.get(backtest_id)

        except Exception as e:
            logger.error(f"Custom backtest {backtest_id} failed: {e}")
            db.backtests.set_status(backtest_id, "failed", error=str(e))
            raise
