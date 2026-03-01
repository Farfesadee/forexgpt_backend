
"""
api/routes/backtest.py — Backtesting REST API.

Endpoints:
  POST   /backtest/run               ← PRIMARY: run a backtest synchronously
  GET    /backtest/results/{id}      ← PRIMARY: fetch result + equity curve + interpretation
  GET    /backtest/results           List all completed backtests for this user
  GET    /backtest/results/{id}/trades  Paginated trade ledger
  PATCH  /backtest/results/{id}      Save/annotate a result
  DELETE /backtest/results/{id}      Delete a backtest record

  GET    /backtest/status            Endpoint health + capability info

All endpoints require: Authorization: Bearer <access_token>

Note on sync vs async execution:
  Run is executed synchronously — yfinance + vectorised simulation is fast (<5s for 1yr/1h).
  For longer backtests (multi-year, tick data), a task queue (Celery/ARQ) would be appropriate.
  The backtests.status column (pending→running→completed) is designed to support async
  execution — the route transitions through all states even in sync mode.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.middleware.auth_middleware import get_current_user
from models.user import JWTPayload
from models.backtest import (
    BacktestRunRequest,
    BacktestResponse,
    BacktestListResponse,
    BacktestTradeListResponse,
    BacktestUpdateRequest,
    BacktestFilterParams,
)
import services.backtest_service as backtest_service

logger = logging.getLogger(__name__)
router = APIRouter()

# POST /backtest/run 
@router.post(
    "/run",
    response_model=BacktestResponse,
    status_code=status.HTTP_200_OK,
    summary="Run a backtest",
    description="""
Execute a full backtest of a trading strategy against historical Forex data.

**Strategy source — provide one of:**
- `strategy_id` : ID of a saved strategy from your code library
- `code`        : Inline Python strategy code

**Strategy code contract:**
```python
STRATEGY_PARAMS = {
    "fast_period": 20,
    "slow_period": 50,
    "stop_loss_pips": 25,
}

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    \"\"\"
    df contains OHLCV columns: Open, High, Low, Close, Volume
    Must return df with:
      df['signal']         — int: 1=long, -1=short, 0=flat
      df['stop_loss_pips'] — float: stop distance from entry in pips
    \"\"\"
    ...
    return df
```

**Engine pipeline:**
1. OHLCV data fetched from yfinance
2. `generate_signals(df)` executed in restricted sandbox
3. Trades simulated with realistic spread + commission + slippage + swap costs
4. Entry on next bar's open after signal (no look-ahead bias)
5. Performance metrics computed (Sharpe, Sortino, Calmar, drawdown, etc.)
6. Plain-English educational interpretation generated

**Returns immediately** with full results — synchronous execution typically under 5s.
""",
)
async def run_backtest(
    body: BacktestRunRequest,
    user: JWTPayload = Depends(get_current_user),
):
    """
    POST body example:
    ```json
    {
      "strategy_id": "uuid-of-saved-strategy",
      "pair": "EUR/USD",
      "start_date": "2023-01-01",
      "end_date": "2024-01-01",
      "timeframe": "1h",
      "initial_capital": 10000,
      "leverage": 30,
      "costs": {
        "spread_pips": 1.0,
        "commission_per_lot": 3.5,
        "slippage_pips": 0.5
      },
      "save_results": false
    }
    ```

    Or with inline code:
    ```json
    {
      "code": "STRATEGY_PARAMS = {}\\ndef generate_signals(df):\\n    ...",
      "pair": "EUR/USD",
      "start_date": "2023-01-01",
      "end_date": "2024-01-01",
      "timeframe": "1h"
    }
    ```

    Errors:
    - 400: Invalid strategy code (syntax error, missing generate_signals, bad output)
    - 404: strategy_id not found or not owned by this user
    - 422: Validation error (bad date range, unknown pair format, etc.)
    - 503: yfinance data unavailable for this pair/date range
    """
    try:
        return await backtest_service.run(user_id=user.user_id, request=body)

    except ValueError as e:
        # Strategy not found, ownership check failed
        err = str(e)
        if "not found" in err.lower():
            raise HTTPException(status_code=404, detail=err)
        raise HTTPException(status_code=400, detail=err)

    except RuntimeError as e:
        # Engine errors: bad code, no data, strategy execution failure
        err = str(e)
        if "No data returned" in err or "ticker" in err.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Market data unavailable: {err}",
            )
        raise HTTPException(status_code=400, detail=err)

    except Exception as e:
        logger.error(f"Backtest run error for user {user.user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during backtesting. Please try again.",
        )

# GET /backtest/results/{id} 
@router.get(
    "/results/{backtest_id}",
    response_model=BacktestResponse,
    summary="Get backtest results",
    description="""
Retrieve the full results of a completed backtest run.

Includes:
- **metrics** : Full set of 14 performance metrics (Sharpe, Sortino, Calmar, win rate, etc.)
- **equity_curve** : Time series of portfolio value and drawdown at each bar
- **educational_analysis** : Plain-English interpretation of results
- **improvement_suggestions** : Actionable suggestions based on metric analysis
- **costs** : The cost model used (spread, commission, slippage)

The denormalized top-level fields (`sharpe_ratio`, `total_return_pct`, etc.) give quick access
to key metrics without parsing the `metrics` JSONB object.
""",
)
async def get_result(
    backtest_id: str,
    user: JWTPayload = Depends(get_current_user),
):
    """
    Returns 404 if the backtest doesn't exist or belongs to another user.
    Returns the full BacktestResponse regardless of status (pending/running/failed/completed).
    """
    try:
        return await backtest_service.get_result(backtest_id, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Get result error {backtest_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve backtest results.")

# GET /backtest/results
@router.get(
    "/results",
    response_model=BacktestListResponse,
    summary="List your backtests",
)
async def list_results(
    pair:   str | None = Query(None, description="Filter by pair, e.g. 'EURUSD=X'."),
    limit:  int        = Query(20, ge=1, le=100),
    offset: int        = Query(0,  ge=0),
    user:   JWTPayload = Depends(get_current_user),
):
    """
    Returns a compact list of all completed backtests for this user.
    Each item includes key metrics (Sharpe, return, drawdown) for quick comparison.
    Ordered by `created_at DESC` (most recent first).
    """
    try:
        return await backtest_service.list_results(
            user_id=user.user_id,
            pair=pair,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"List results error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list backtests.")

# GET /backtest/results/{id}/trades 
@router.get(
    "/results/{backtest_id}/trades",
    response_model=BacktestTradeListResponse,
    summary="Get individual trade ledger for a backtest",
)
async def get_trades(
    backtest_id: str,
    limit:  int        = Query(500, ge=1, le=5000),
    offset: int        = Query(0,   ge=0),
    user:   JWTPayload = Depends(get_current_user),
):
    """
    Returns the individual trade ledger for a backtest.

    Trade ledger is separate from the main backtest row because high-frequency
    strategies can generate thousands of trades — fetching them separately
    avoids bloating the results endpoint.

    Each trade includes:
    - direction (long/short)
    - entry/exit time and price
    - lot size, P&L in pips and USD
    - trade duration in hours
    """
    try:
        return await backtest_service.get_trades(backtest_id, user.user_id, limit, offset)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Get trades error {backtest_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve trade ledger.")

# PATCH /backtest/results/{id} 
@router.patch(
    "/results/{backtest_id}",
    response_model=BacktestResponse,
    summary="Save or annotate a backtest result",
)
async def update_result(
    backtest_id: str,
    body: BacktestUpdateRequest,
    user: JWTPayload = Depends(get_current_user),
):
    """
    Update mutable fields on a backtest:
    - `is_saved`   : Mark/unmark as saved (shows in saved results view)
    - `user_notes` : Add personal notes about this backtest run

    All other fields are immutable once the backtest is completed.
    """
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update.")

    try:
        return await backtest_service.update(backtest_id, user.user_id, body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Update backtest error {backtest_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update backtest.")

# DELETE /backtest/results/{id} 

@router.delete(
    "/results/{backtest_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a backtest record",
)
async def delete_result(
    backtest_id: str,
    user: JWTPayload = Depends(get_current_user),
):
    """
    Permanently delete a backtest record and all its associated trades.
    This action is irreversible. Associated strategy is not affected.
    """
    try:
        bt = await backtest_service.get_result(backtest_id, user.user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Backtest not found.")

    try:
        from core.database import db
        db.backtests._bt.delete().eq("id", backtest_id).execute()
    except Exception as e:
        logger.error(f"Delete backtest error {backtest_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete backtest.")

# GET /backtest/status 
@router.get(
    "/status",
    summary="Backtesting engine capabilities and status",
)
async def engine_status(_: JWTPayload = Depends(get_current_user)):
    """
    Returns the backtesting engine capabilities, supported timeframes and pairs.
    """
    try:
        import yfinance as yf
        yfinance_available = True
    except ImportError:
        yfinance_available = False

    return {
        "engine":          "ForexGPT Backtesting Engine v1.0",
        "execution_mode":  "synchronous",
        "yfinance":        yfinance_available,
        "supported_timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"],
        "supported_pairs": [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X",
            "USDCAD=X", "USDCHF=X", "NZDUSD=X", "EURGBP=X",
            "EURJPY=X", "GBPJPY=X",
        ],
        "pair_format":        "Accept EUR/USD, EURUSD, or EURUSD=X — all normalised automatically.",
        "strategy_contract":  {
            "required_function":  "generate_signals(df: pd.DataFrame) -> pd.DataFrame",
            "required_columns":   ["signal (int: -1/0/1)", "stop_loss_pips (float)"],
            "optional_dict":      "STRATEGY_PARAMS = {...}",
            "allowed_imports":    ["pandas (pd)", "numpy (np)", "math"],
        },
        "cost_model":  {
            "spread":     "spread_pips × pip_value per trade",
            "commission": "commission_per_lot per standard lot round-trip",
            "slippage":   "slippage_pips on both entry and exit",
            "swap":       "swap_long/short_pips_per_day for overnight holds",
        },
        "metrics_computed": [
            "total_return_pct", "annualized_return_pct",
            "sharpe_ratio", "sortino_ratio", "calmar_ratio",
            "max_drawdown_pct", "max_drawdown_duration_days",
            "total_trades", "win_rate_pct", "profit_factor",
            "avg_trade_duration_hours",
            "best_trade_pips", "worst_trade_pips",
            "avg_win_pips", "avg_loss_pips", "total_cost_pips",
        ],
    }