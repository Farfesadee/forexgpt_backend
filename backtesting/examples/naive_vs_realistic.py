import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
sys.path.append('..')

from engine.backtest_engine import BacktestEngine
from costs.cost_model import CostModel, get_cost_model
from metrics.performance_metrics import PerformanceMetrics


def generate_sample_data(days: int = 252) -> pd.DataFrame:
    """
    Generate sample price data for demonstration.
    
    Args:
        days: Number of trading days
    
    Returns:
        DataFrame with OHLCV data
    """
    np.random.seed(42)
    
    # Generate dates
    start_date = datetime(2023, 1, 1)
    dates = [start_date + timedelta(days=i) for i in range(days)]
    
    # Generate price series (simple random walk with upward drift)
    returns = np.random.normal(0.0005, 0.02, days)  # 0.05% daily drift, 2% volatility
    prices = 100 * np.exp(np.cumsum(returns))
    
    # OHLC
    high = prices * (1 + np.random.uniform(0, 0.01, days))
    low = prices * (1 - np.random.uniform(0, 0.01, days))
    open_price = prices * (1 + np.random.uniform(-0.005, 0.005, days))
    close = prices
    
    # Volume
    volume = np.random.uniform(100000, 1000000, days)
    
    # Market conditions
    volatility = np.random.uniform(0.8, 1.2, days)  # Volatility multiplier
    liquidity = np.random.uniform(0.7, 1.0, days)    # Liquidity factor
    
    df = pd.DataFrame({
        "date": dates,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "volatility": volatility,
        "liquidity": liquidity
    })
    
    # Calculate volume ratio (trade size vs average volume)
    avg_volume = volume.mean()
    df["volume_ratio"] = volume / avg_volume
    
    return df


def simple_moving_average_strategy(data: pd.DataFrame, fast: int = 10, slow: int = 30) -> str:
    """
    Simple moving average crossover strategy.
    
    Args:
        data: Historical price data
        fast: Fast MA period
        slow: Slow MA period
    
    Returns:
        Signal: "buy", "sell", or "hold"
    """
    if len(data) < slow:
        return "hold"
    
    # Calculate MAs
    fast_ma = data["close"].rolling(fast).mean().iloc[-1]
    slow_ma = data["close"].rolling(slow).mean().iloc[-1]
    
    # Previous MAs
    if len(data) < slow + 1:
        return "hold"
    
    prev_fast_ma = data["close"].rolling(fast).mean().iloc[-2]
    prev_slow_ma = data["close"].rolling(slow).mean().iloc[-2]
    
    # Check for crossover
    if prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma:
        return "buy"
    elif prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma:
        return "sell"
    else:
        return "hold"


def run_naive_backtest(data: pd.DataFrame) -> dict:
    """
    Run NAIVE backtest (NO COSTS).
    This is what most beginners do - and it's WRONG!
    """
    print("\n" + "=" * 80)
    print("NAIVE BACKTEST (WRONG - NO COSTS)")
    print("=" * 80)
    
    # Create engine with ZERO costs
    zero_cost_model = CostModel(
        spread_bps=0.0,
        commission_rate=0.0,
        base_slippage_bps=0.0,
        financing_rate_annual=0.0
    )
    
    engine = BacktestEngine(
        initial_capital=10000,
        cost_model=zero_cost_model,
        position_size_pct=1.0,  # Full capital (unrealistic)
        max_positions=1
    )
    
    # Run backtest
    results = engine.run_backtest(data, simple_moving_average_strategy)
    
    # Calculate metrics
    metrics_calc = PerformanceMetrics(results)
    metrics = metrics_calc.calculate_all_metrics()
    
    # Print results
    print(f"\nInitial Capital: ${results['initial_capital']:,.2f}")
    print(f"Final Capital:   ${results['final_capital']:,.2f}")
    print(f"Total Return:    {metrics['total_return_pct']:.2f}%")
    print(f"CAGR:            {metrics['cagr_pct']:.2f}%")
    print(f"Sharpe Ratio:    {metrics['sharpe_ratio']:.2f}")
    print(f"Max Drawdown:    {metrics['max_drawdown_pct']:.2f}%")
    print(f"\nTotal Trades:    {metrics['total_trades']}")
    print(f"Win Rate:        {metrics['win_rate_pct']:.2f}%")
    print(f"Profit Factor:   {metrics['profit_factor']:.2f}")
    
    print(f"\n  WARNING: This backtest ignores all trading costs!")
    print(f"             Results are UNREALISTIC and MISLEADING.")
    
    return results, metrics


def run_realistic_backtest(data: pd.DataFrame) -> dict:
    """
    Run REALISTIC backtest (WITH COSTS).
    This is the correct way to backtest!
    """
    print("\n" + "=" * 80)
    print("REALISTIC BACKTEST (CORRECT - WITH COSTS)")
    print("=" * 80)
    
    # Use realistic cost model
    realistic_cost_model = get_cost_model("forex_retail")
    
    # Print cost assumptions
    print(f"\nCost Model Parameters:")
    print(f"  Spread:           {realistic_cost_model.spread_bps} bps")
    print(f"  Slippage:         {realistic_cost_model.base_slippage_bps} bps")
    print(f"  Commission:       ${realistic_cost_model.commission_rate}")
    print(f"  Financing (p.a.): {realistic_cost_model.financing_rate_annual*100}%")
    
    engine = BacktestEngine(
        initial_capital=10000,
        cost_model=realistic_cost_model,
        position_size_pct=0.1,  # Realistic 10% per trade
        max_positions=1
    )
    
    # Run backtest
    results = engine.run_backtest(data, simple_moving_average_strategy)
    
    # Calculate metrics
    metrics_calc = PerformanceMetrics(results)
    metrics = metrics_calc.calculate_all_metrics()
    
    # Print results
    print(f"\nInitial Capital: ${results['initial_capital']:,.2f}")
    print(f"Final Capital:   ${results['final_capital']:,.2f}")
    print(f"Total Return:    {metrics['total_return_pct']:.2f}%")
    print(f"CAGR:            {metrics['cagr_pct']:.2f}%")
    print(f"Sharpe Ratio:    {metrics['sharpe_ratio']:.2f}")
    print(f"Max Drawdown:    {metrics['max_drawdown_pct']:.2f}%")
    
    print(f"\nTotal Trades:    {metrics['total_trades']}")
    print(f"Win Rate:        {metrics['win_rate_pct']:.2f}%")
    print(f"Profit Factor:   {metrics['profit_factor']:.2f}")
    
    print(f"\n COST BREAKDOWN:")
    print(f"  Total Costs:     ${metrics['total_costs']:,.2f}")
    print(f"  Spread Costs:    ${metrics['spread_costs']:,.2f}")
    print(f"  Slippage:        ${metrics['slippage_costs']:,.2f}")
    print(f"  Commission:      ${metrics['commission_costs']:,.2f}")
    print(f"  Financing:       ${metrics['financing_costs']:,.2f}")
    print(f"  Cost % of Gross: {metrics['costs_pct_of_gross_pnl']:.2f}%")
    
    print(f"\n This backtest includes realistic trading costs.")
    
    return results, metrics


def compare_backtests(naive_results: dict, naive_metrics: dict, 
                     realistic_results: dict, realistic_metrics: dict):
    """Compare naive vs realistic backtest results."""
    print("\n" + "=" * 80)
    print("COMPARISON: NAIVE vs REALISTIC")
    print("=" * 80)
    
    naive_return = naive_metrics['total_return_pct']
    realistic_return = realistic_metrics['total_return_pct']
    difference = naive_return - realistic_return
    
    print(f"\n RETURNS:")
    print(f"  Naive Backtest:      {naive_return:>8.2f}%")
    print(f"  Realistic Backtest:  {realistic_return:>8.2f}%")
    print(f"  Difference:          {difference:>8.2f}%")
    print(f"  Overestimation:      {(difference/realistic_return*100) if realistic_return != 0 else 0:>8.1f}%")
    
    print(f"\n KEY INSIGHTS:")
    
    if difference > 0:
        print(f"  • Naive backtest OVERESTIMATED returns by {difference:.2f}%")
        print(f"  • Trading costs reduced returns by {realistic_metrics['costs_pct_of_gross_pnl']:.1f}% of gross P&L")
        print(f"  • Total costs: ${realistic_metrics['total_costs']:,.2f}")
    
    print(f"\n  LESSON:")
    print(f"  Always include realistic costs in your backtests!")
    print(f"  The difference between naive and realistic can be the difference")
    print(f"  between a profitable strategy and a money-losing one.")
    
    # Show sample trade comparison
    if len(realistic_results["trades"]) > 0:
        trade = realistic_results["trades"][0]
        
        print(f"\n SAMPLE TRADE BREAKDOWN:")
        print(f"  Entry Price:       ${trade['entry_price']:.4f}")
        print(f"  Exit Price:        ${trade['exit_price']:.4f}")
        print(f"  Gross P&L:         ${trade['gross_pnl']:,.2f}")
        print(f"  - Spread Cost:     ${trade['spread_cost']:,.2f}")
        print(f"  - Slippage:        ${trade['slippage_cost']:,.2f}")
        print(f"  - Commission:      ${trade['commission']:,.2f}")
        print(f"  - Financing:       ${trade['financing_cost']:,.2f}")
        print(f"  = Net P&L:         ${trade['net_pnl']:,.2f}")
        print(f"  Return:            {trade['return_pct']:.2f}%")


def main():
    """Run complete example."""
    print("=" * 80)
    print("BACKTESTING EXAMPLE: NAIVE vs REALISTIC")
    print("=" * 80)
    print("\nThis example demonstrates WHY you must include realistic costs")
    print("in your backtests. Most beginners make this mistake!")
    
    # Generate sample data
    print("\nGenerating sample price data (1 year, daily)...")
    data = generate_sample_data(days=252)
    print(f" Generated {len(data)} days of data")
    print(f"  Price range: ${data['close'].min():.2f} - ${data['close'].max():.2f}")
    
    # Run naive backtest
    naive_results, naive_metrics = run_naive_backtest(data)
    
    # Run realistic backtest
    realistic_results, realistic_metrics = run_realistic_backtest(data)
    
    # Compare results
    compare_backtests(naive_results, naive_metrics, 
                     realistic_results, realistic_metrics)
    
    print("\n" + "=" * 80)
    print("EXAMPLE COMPLETE")
    print("=" * 80)
    print("  - Forex (retail & institutional)")
   


if __name__ == "__main__":
    main()
