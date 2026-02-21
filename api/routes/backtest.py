import logging
from fastapi import APIRouter, HTTPException, Depends
from models.backtest import BacktestRequest, BacktestResponse, BacktestResult, CostBreakdown
from services.backtest_service import run_backtest
from services.auth_service import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/backtest", tags=["Backtesting"])


@router.post("/run", response_model=BacktestResponse)
async def run_backtest_endpoint(
    body: BacktestRequest,
    user: dict = Depends(verify_token),
):
    logger.info(f"Backtest requested by user: {user['user_id']}")
    result = await run_backtest(
        request=body.model_dump(),
        user_id=user["user_id"],
    )

    def build_result(data: dict) -> BacktestResult:
        return BacktestResult(
            gross_profit_pips=data["gross_profit_pips"],
            gross_profit_usd=data["gross_profit_usd"],
            net_profit_pips=data["net_profit_pips"],
            net_profit_usd=data["net_profit_usd"],
            cost_breakdown=CostBreakdown(**data["cost_breakdown"]),
            cost_impact_percent=data["cost_impact_percent"],
            win=data["win"],
        )

    return BacktestResponse(
        naive=build_result(result["naive"]),
        realistic=build_result(result["realistic"]),
        backtest_id=result.get("backtest_id"),
    )


@router.get("/results/{backtest_id}")
async def get_backtest_results(
    backtest_id: str,
    user: dict = Depends(verify_token),
):
    try:
        from core.database import get_supabase
        db = get_supabase()
        record = db.table("backtests").select("*").eq("id", backtest_id).execute()
        if not record.data:
            raise HTTPException(status_code=404, detail="Backtest not found.")
        return record.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))