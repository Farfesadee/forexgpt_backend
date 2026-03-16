"""
api/routes/backtest.py
FastAPI endpoints for the backtest service.
Matches the style of api/routes/signals.py and api/routes/mentor.py
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from models.backtest import (
    RunBacktestRequest,
    RunBacktestResponse,
    SavedBacktestResponse,
    BacktestDetailResponse,
    DeleteBacktestResponse,
    RunCustomBacktestRequest,      
    RunCustomBacktestResponse,
)
from core.dependencies import get_backtest_service
from api.middleware.auth_middleware import get_current_user
from models.user import JWTPayload

router  = APIRouter(prefix="/backtest", tags=["backtest"])
service = get_backtest_service()

def _assert_user_access(requested_user_id: str, user: JWTPayload) -> None:
    if requested_user_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own resources.",
        )
        
# ── Run a backtest ────────────────────────────────────────────────────────────

@router.post("/run", response_model=RunBacktestResponse)
async def run_backtest(request: RunBacktestRequest, 
                       user: JWTPayload = Depends(get_current_user),):
    """
    Run a full backtest:
    fetch data → run engine → calculate metrics → save to Supabase.
    """
    try:
        result = await service.run_backtest(
            user_id=request.user_id,
            strategy_id=request.strategy_id,
            pair=request.pair,
            start_date=request.start_date,
            end_date=request.end_date,
            timeframe=request.timeframe,
            initial_capital=request.initial_capital,
            strategy_name=request.strategy_name,
            strategy_params=request.strategy_params,
            cost_preset=request.cost_preset,
            position_size_pct=request.position_size_pct,
            data_source=request.data_source,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        # raise HTTPException(
            # status_code=503,
            # detail="Backtest service is temporarily unavailable. Please try again."
        # )


# ── List all backtests for a user ─────────────────────────────────────────────

@router.get("/user/{user_id}", response_model=list[SavedBacktestResponse])
async def get_user_backtests(
    user_id: str,
    pair:    Optional[str] = None,
    limit:   int = 20,
    user: JWTPayload = Depends(get_current_user),
):
    """Get all completed backtests for a user, newest first."""
    try:
        return await service.get_user_backtests(user_id, pair=pair, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Get a single backtest ─────────────────────────────────────────────────────

@router.get("/user/{user_id}/{backtest_id}", response_model=BacktestDetailResponse)
async def get_backtest(backtest_id: str, user_id: str, user: JWTPayload = Depends(get_current_user),):
    """Get full detail of a single backtest including metrics and equity curve."""
    try:
        backtest = await service.get_backtest_by_id(backtest_id, user_id)
        if backtest is None:
            raise HTTPException(status_code=404, detail="Backtest not found")
        return backtest
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Get trades for a backtest ─────────────────────────────────────────────────

@router.get("/user/{user_id}/{backtest_id}/trades")
async def get_backtest_trades(
    backtest_id: str,
    user_id:     str,
    limit:       int = 500,
    offset:      int = 0,
    user: JWTPayload = Depends(get_current_user),
):
    """Get individual trade log for a backtest."""
    try:
        trades = await service.get_backtest_trades(
            backtest_id, user_id, limit=limit, offset=offset
        )
        return {"trades": trades, "total": len(trades)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Delete a backtest ─────────────────────────────────────────────────────────

@router.delete("/{user_id}/{backtest_id}", response_model=DeleteBacktestResponse)
async def delete_backtest(backtest_id: str, user_id: str, user: JWTPayload = Depends(get_current_user),):
    """Delete a saved backtest."""
    try:
        deleted = await service.delete_backtest(backtest_id, user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Backtest not found")
        return {"message": "Backtest deleted successfully", "backtest_id": backtest_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Run a custom strategy backtest ───────────────────────────────────────────

@router.post("/run/custom", response_model=RunCustomBacktestResponse)
async def run_custom_backtest(
    request: RunCustomBacktestRequest,
    user:    JWTPayload = Depends(get_current_user),
):
    """
    Execute user-generated strategy code against historical price data.

    The code must define a generate_signals(data) function.
    Results are saved to the backtests table with strategy_name='custom'
    and appear in the user's backtest history alongside parameterised runs.

    Flow: validate → fetch data → sandbox execute → metrics → save → return
    """
    _assert_user_access(request.user_id, user)

    try:
        result = await service.run_custom_strategy(
            user_id=request.user_id,
            custom_code=request.custom_code,
            pair=request.pair,
            start_date=request.start_date,
            end_date=request.end_date,
            timeframe=request.timeframe,
            initial_capital=request.initial_capital,
            position_size_pct=request.position_size_pct,
            data_source=request.data_source,
        )
        return result

    except ValueError as e:
        # Code validation errors and strategy runtime errors — user's fault
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        # Data fetch failures, timeout, unexpected errors
        raise HTTPException(status_code=500, detail=str(e))