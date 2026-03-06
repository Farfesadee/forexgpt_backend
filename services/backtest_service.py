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
            f"Supported: rsi, moving_average_crossover, bollinger_bands, macd"
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
            strategy_name:     rsi | moving_average_crossover | bollinger_bands | macd
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
