import logging
from core.database import get_supabase

logger = logging.getLogger(__name__)

# ─── Cost Model Constants ─────────────────────────────────────
# Based on typical retail forex broker costs

COST_MODEL = {
    "normal": {
        "spread_pips": 2.0,      # 2 pips each side = 4 pips total
        "slippage_pips": 1.0,    # 1 pip each side = 2 pips total
    },
    "volatile": {
        "spread_pips": 4.0,      # Spreads widen in volatile markets
        "slippage_pips": 2.0,
    },
}

COMMISSION_PER_TRADE_USD = 5.0   # $5 per side = $10 round trip
FINANCING_RATE_PER_DAY = 0.001   # 0.1% per day


# ─── Core Calculations ───────────────────────────────────────

def _price_diff_to_pips(entry: float, exit: float, direction: str) -> float:
    """Converts price difference to pips. 1 pip = 0.0001 for most pairs."""
    diff = exit - entry if direction == "LONG" else entry - exit
    return round(diff / 0.0001, 2)


def _pips_to_usd(pips: float, position_size_lots: float) -> float:
    """1 lot = 100,000 units. 1 pip on 1 lot = $10."""
    return round(pips * 10 * position_size_lots, 2)


def _calculate_commission_pips(
    entry_price: float,
    position_size_lots: float,
) -> float:
    """Converts $10 round-trip commission into pip equivalent."""
    position_value_usd = position_size_lots * 100_000 * entry_price
    commission_total = COMMISSION_PER_TRADE_USD * 2   # entry + exit
    ratio = commission_total / position_value_usd
    return round(ratio * 10_000, 4)


def _calculate_financing_pips(days_held: int) -> float:
    """Financing cost in pips based on days held."""
    return round(FINANCING_RATE_PER_DAY * days_held, 4)


# ─── Naive Backtest ───────────────────────────────────────────

def _run_naive(
    entry_price: float,
    exit_price: float,
    direction: str,
    position_size_lots: float,
) -> dict:
    """
    Naive backtest — ignores all trading costs.
    This is what most basic backtesting tools show.
    """
    gross_pips = _price_diff_to_pips(entry_price, exit_price, direction)
    gross_usd = _pips_to_usd(gross_pips, position_size_lots)

    return {
        "gross_profit_pips": gross_pips,
        "gross_profit_usd": gross_usd,
        "net_profit_pips": gross_pips,
        "net_profit_usd": gross_usd,
        "cost_breakdown": {
            "spread_pips": 0.0,
            "slippage_pips": 0.0,
            "commission_pips": 0.0,
            "financing_pips": 0.0,
            "total_cost_pips": 0.0,
        },
        "cost_impact_percent": 0.0,
        "win": gross_pips > 0,
    }


# ─── Realistic Backtest ───────────────────────────────────────

def _run_realistic(
    entry_price: float,
    exit_price: float,
    direction: str,
    position_size_lots: float,
    days_held: int,
    market_condition: str,
) -> dict:
    """
    Realistic backtest — applies spread, slippage, commission, financing.
    This is what real trading actually looks like.
    """
    gross_pips = _price_diff_to_pips(entry_price, exit_price, direction)
    gross_usd = _pips_to_usd(gross_pips, position_size_lots)

    # Cost components
    costs = COST_MODEL.get(market_condition, COST_MODEL["normal"])
    spread_pips = costs["spread_pips"] * 2          # Entry + exit
    slippage_pips = costs["slippage_pips"] * 2      # Entry + exit
    commission_pips = _calculate_commission_pips(entry_price, position_size_lots)
    financing_pips = _calculate_financing_pips(days_held)

    total_cost_pips = round(
        spread_pips + slippage_pips + commission_pips + financing_pips, 4
    )

    net_pips = round(gross_pips - total_cost_pips, 2)
    net_usd = _pips_to_usd(net_pips, position_size_lots)

    cost_impact_percent = (
        round((total_cost_pips / abs(gross_pips)) * 100, 2)
        if gross_pips != 0 else 0.0
    )

    return {
        "gross_profit_pips": gross_pips,
        "gross_profit_usd": gross_usd,
        "net_profit_pips": net_pips,
        "net_profit_usd": net_usd,
        "cost_breakdown": {
            "spread_pips": spread_pips,
            "slippage_pips": slippage_pips,
            "commission_pips": commission_pips,
            "financing_pips": financing_pips,
            "total_cost_pips": total_cost_pips,
        },
        "cost_impact_percent": cost_impact_percent,
        "win": net_pips > 0,
    }


# ─── Main Service Function ────────────────────────────────────

async def run_backtest(request: dict, user_id: str | None = None) -> dict:
    """
    Runs both naive and realistic backtests and returns a comparison.
    Saves the result to Supabase if user is authenticated.
    """
    naive = _run_naive(
        entry_price=request["entry_price"],
        exit_price=request["exit_price"],
        direction=request["direction"],
        position_size_lots=request["position_size_lots"],
    )

    realistic = _run_realistic(
        entry_price=request["entry_price"],
        exit_price=request["exit_price"],
        direction=request["direction"],
        position_size_lots=request["position_size_lots"],
        days_held=request["days_held"],
        market_condition=request.get("market_condition", "normal"),
    )

    logger.info(
        f"Backtest complete — naive: {naive['net_profit_usd']} USD, "
        f"realistic: {realistic['net_profit_usd']} USD, "
        f"cost impact: {realistic['cost_impact_percent']}%"
    )

    # Save to Supabase if user is authenticated
    backtest_id = None
    if user_id:
        try:
            db = get_supabase()
            record = db.table("backtests").insert({
                "user_id": user_id,
                "currency_pair": request["currency_pair"],
                "direction": request["direction"],
                "entry_price": request["entry_price"],
                "exit_price": request["exit_price"],
                "position_size_lots": request["position_size_lots"],
                "days_held": request["days_held"],
                "market_condition": request.get("market_condition", "normal"),
                "naive_profit_usd": naive["net_profit_usd"],
                "realistic_profit_usd": realistic["net_profit_usd"],
                "cost_impact_percent": realistic["cost_impact_percent"],
            }).execute()
            backtest_id = record.data[0]["id"]
            logger.info(f"Backtest saved to Supabase with id: {backtest_id}")
        except Exception as e:
            logger.warning(f"Could not save backtest to DB: {e}")

    return {
        "naive": naive,
        "realistic": realistic,
        "backtest_id": backtest_id,
    }