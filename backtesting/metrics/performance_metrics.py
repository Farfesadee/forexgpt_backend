"""
Performance Metrics Calculator
Pure Python/pandas — NO LLM involvement.

Calculates all performance and risk metrics from backtest results produced
by BacktestEngine.get_results().

Expected input format (from BacktestEngine.get_results()):
{
    "initial_capital": float,
    "final_capital": float,
    "total_return": float,          # raw percentage
    "num_trades": int,
    "trades": [
        {
            "entry_date": datetime,
            "exit_date": datetime,
            "entry_price": float,
            "exit_price": float,
            "quantity": float,
            "side": str,
            "holding_days": int,
            "gross_pnl": float,
            "net_pnl": float,
            "return_pct": float,
            "spread_cost": float,
            "slippage_cost": float,
            "commission": float,
            "financing_cost": float,
            "exchange_fees": float,
            "total_cost": float
        },
        ...
    ],
    "equity_curve": [
        {
            "date": datetime,
            "price": float,
            "capital": float,
            "unrealized_pnl": float,
            "total_equity": float,
            "num_positions": int
        },
        ...
    ]
}
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """
    Calculates comprehensive performance and risk metrics from backtest results.

    Usage:
        metrics_calc = PerformanceMetrics(backtest_results)
        metrics = metrics_calc.calculate_all_metrics()
    """

    def __init__(self, results: Dict, risk_free_rate: float = 0.05):
        """
        Initialize with backtest results from BacktestEngine.get_results()

        Args:
            results: Dict from BacktestEngine.get_results()
            risk_free_rate: Annual risk-free rate for Sharpe/Sortino (default 5%)
        """
        self.results = results
        self.risk_free_rate = risk_free_rate

        self.initial_capital = results.get("initial_capital", 10000.0)
        self.final_capital = results.get("final_capital", self.initial_capital)
        self.trades = results.get("trades", [])
        self.equity_curve = results.get("equity_curve", [])

        # Build equity series once for reuse
        self._equity_series = self._build_equity_series()

    # =========================================================================
    # PUBLIC INTERFACE
    # =========================================================================

    def calculate_all_metrics(self) -> Dict:
        """
        Calculate all metrics and return as a flat dict.
        This is the main method called by naive_vs_realistic.py.

        Returns:
            Dict with all metrics ready for display/reporting
        """
        if not self.trades:
            logger.warning("No trades found in backtest results.")
            return self._empty_metrics()

        metrics = {}
        metrics.update(self._return_metrics())
        metrics.update(self._trade_metrics())
        metrics.update(self._risk_metrics())
        metrics.update(self._ratio_metrics())
        metrics.update(self._cost_metrics())

        return metrics

    # =========================================================================
    # RETURN METRICS
    # =========================================================================

    def _return_metrics(self) -> Dict:
        """Total return, CAGR, and annualized return."""
        total_return_pct = (
            (self.final_capital - self.initial_capital) / self.initial_capital * 100
        )

        # CAGR — compound annual growth rate
        n_days = len(self._equity_series)
        n_years = n_days / 252  # trading days per year

        if n_years > 0 and self.final_capital > 0:
            cagr_pct = (
                (self.final_capital / self.initial_capital) ** (1 / n_years) - 1
            ) * 100
        else:
            cagr_pct = 0.0

        return {
            "total_return_pct": round(total_return_pct, 2),
            "cagr_pct": round(cagr_pct, 2),
            "initial_capital": round(self.initial_capital, 2),
            "final_capital": round(self.final_capital, 2),
        }

    # =========================================================================
    # TRADE METRICS
    # =========================================================================

    def _trade_metrics(self) -> Dict:
        """Win rate, profit factor, average win/loss, trade counts."""
        total_trades = len(self.trades)
        if total_trades == 0:
            return {"total_trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0}

        winning = [t for t in self.trades if t.get("net_pnl", 0) > 0]
        losing  = [t for t in self.trades if t.get("net_pnl", 0) <= 0]

        win_count  = len(winning)
        loss_count = len(losing)
        win_rate   = win_count / total_trades

        gross_profit = sum(t["net_pnl"] for t in winning)
        gross_loss   = abs(sum(t["net_pnl"] for t in losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        avg_win  = np.mean([t["net_pnl"] for t in winning]) if winning else 0.0
        avg_loss = np.mean([t["net_pnl"] for t in losing])  if losing  else 0.0
        avg_rr   = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

        avg_holding = np.mean([t.get("holding_days", 0) for t in self.trades])

        total_pnl = sum(t.get("net_pnl", 0) for t in self.trades)

        return {
            "total_trades":   total_trades,
            "winning_trades": win_count,
            "losing_trades":  loss_count,
            "win_rate":       round(win_rate, 4),
            "win_rate_pct":   round(win_rate * 100, 2),
            "gross_profit":   round(gross_profit, 2),
            "gross_loss":     round(gross_loss, 2),
            "profit_factor":  round(profit_factor, 2),
            "avg_win":        round(avg_win, 2),
            "avg_loss":       round(avg_loss, 2),
            "avg_risk_reward":round(avg_rr, 2),
            "avg_holding_days": round(avg_holding, 1),
            "total_pnl":      round(total_pnl, 2),
        }

    # =========================================================================
    # RISK METRICS
    # =========================================================================

    def _risk_metrics(self) -> Dict:
        """Drawdown, volatility."""
        if self._equity_series.empty:
            return {
                "max_drawdown_pct": 0.0,
                "avg_drawdown_pct": 0.0,
                "volatility_annual_pct": 0.0,
            }

        # Drawdown
        rolling_max = self._equity_series.cummax()
        drawdown_series = (self._equity_series - rolling_max) / rolling_max * 100
        max_drawdown_pct = drawdown_series.min()    # most negative
        avg_drawdown_pct = drawdown_series[drawdown_series < 0].mean() if (drawdown_series < 0).any() else 0.0

        # Volatility
        daily_returns = self._equity_series.pct_change().dropna()
        volatility_annual_pct = daily_returns.std() * np.sqrt(252) * 100

        return {
            "max_drawdown_pct":      round(max_drawdown_pct, 2),
            "avg_drawdown_pct":      round(avg_drawdown_pct, 2),
            "volatility_annual_pct": round(volatility_annual_pct, 2),
        }

    # =========================================================================
    # RATIO METRICS
    # =========================================================================

    def _ratio_metrics(self) -> Dict:
        """Sharpe, Sortino, Calmar ratios."""
        if self._equity_series.empty or len(self._equity_series) < 2:
            return {"sharpe_ratio": 0.0, "sortino_ratio": 0.0, "calmar_ratio": 0.0}

        daily_returns = self._equity_series.pct_change().dropna()
        daily_rf = self.risk_free_rate / 252
        excess_returns = daily_returns - daily_rf
        std = daily_returns.std()

        # Sharpe
        sharpe = (excess_returns.mean() / std * np.sqrt(252)) if std > 0 else 0.0

        # Sortino (downside deviation only)
        downside = daily_returns[daily_returns < daily_rf]
        downside_std = downside.std() if len(downside) > 0 else 0.0
        sortino = (excess_returns.mean() / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0

        # Calmar
        cagr_pct = self._return_metrics()["cagr_pct"]
        max_dd = self._risk_metrics()["max_drawdown_pct"]
        calmar = (cagr_pct / abs(max_dd)) if max_dd != 0 else 0.0

        return {
            "sharpe_ratio":  round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "calmar_ratio":  round(calmar, 4),
        }

    # =========================================================================
    # COST METRICS
    # =========================================================================

    def _cost_metrics(self) -> Dict:
        """Total and breakdown of all trading costs."""
        if not self.trades:
            return {
                "total_costs": 0.0,
                "spread_costs": 0.0,
                "slippage_costs": 0.0,
                "commission_costs": 0.0,
                "financing_costs": 0.0,
                "exchange_fee_costs": 0.0,
                "costs_pct_of_gross_pnl": 0.0,
            }

        total_costs      = sum(t.get("total_cost", 0)      for t in self.trades)
        spread_costs     = sum(t.get("spread_cost", 0)     for t in self.trades)
        slippage_costs   = sum(t.get("slippage_cost", 0)   for t in self.trades)
        commission_costs = sum(t.get("commission", 0)      for t in self.trades)
        financing_costs  = sum(t.get("financing_cost", 0)  for t in self.trades)
        exchange_costs   = sum(t.get("exchange_fees", 0)   for t in self.trades)

        gross_pnl = sum(t.get("gross_pnl", 0) for t in self.trades)
        costs_pct = (total_costs / abs(gross_pnl) * 100) if gross_pnl != 0 else 0.0

        return {
            "total_costs":           round(total_costs, 2),
            "spread_costs":          round(spread_costs, 2),
            "slippage_costs":        round(slippage_costs, 2),
            "commission_costs":      round(commission_costs, 2),
            "financing_costs":       round(financing_costs, 2),
            "exchange_fee_costs":    round(exchange_costs, 2),
            "costs_pct_of_gross_pnl": round(costs_pct, 2),
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _build_equity_series(self) -> pd.Series:
        """Build a pandas Series of total equity from the equity curve."""
        if not self.equity_curve:
            return pd.Series(dtype=float)

        dates  = [row["date"]         for row in self.equity_curve]
        values = [row["total_equity"] for row in self.equity_curve]

        return pd.Series(values, index=pd.to_datetime(dates))

    def _empty_metrics(self) -> Dict:
        """Return zeroed metrics when there are no trades."""
        return {
            "total_return_pct":      0.0,
            "cagr_pct":              0.0,
            "initial_capital":       round(self.initial_capital, 2),
            "final_capital":         round(self.final_capital, 2),
            "total_trades":          0,
            "winning_trades":        0,
            "losing_trades":         0,
            "win_rate":              0.0,
            "win_rate_pct":          0.0,
            "gross_profit":          0.0,
            "gross_loss":            0.0,
            "profit_factor":         0.0,
            "avg_win":               0.0,
            "avg_loss":              0.0,
            "avg_risk_reward":       0.0,
            "avg_holding_days":      0.0,
            "total_pnl":             0.0,
            "max_drawdown_pct":      0.0,
            "avg_drawdown_pct":      0.0,
            "volatility_annual_pct": 0.0,
            "sharpe_ratio":          0.0,
            "sortino_ratio":         0.0,
            "calmar_ratio":          0.0,
            "total_costs":           0.0,
            "spread_costs":          0.0,
            "slippage_costs":        0.0,
            "commission_costs":      0.0,
            "financing_costs":       0.0,
            "exchange_fee_costs":    0.0,
            "costs_pct_of_gross_pnl": 0.0,
        }
