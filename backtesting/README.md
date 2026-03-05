# 📈 Realistic Backtesting Framework

A production-ready backtesting engine with **realistic cost modeling** — because paper trading profits don't count if they disappear in real trading costs.

## 🎯 Why This Matters

**Most backtests are WRONG** because they ignore real trading costs:

```
❌ Naive Backtest (Wrong):
Entry: 1.0950 → Exit: 1.1000
Profit: 50 pips
Return: 4.8%

✅ Realistic Backtest (Correct):
Entry: 1.0950
- Spread cost: -2 pips
Exit: 1.1000  
- Spread cost: -2 pips
- Slippage: -1 pip
- Commission: -0.5 pip
Net profit: 44.5 pips
Return: 4.3% (10% lower!)
```

**This framework gives you the REAL numbers.**

## ✨ Features

### 💰 Comprehensive Cost Modeling
- **Spreads** - Bid-ask spread costs
- **Slippage** - Market impact & execution slippage
- **Commissions** - Broker/exchange fees
- **Financing** - Overnight holding costs (swap/margin interest)
- **Exchange Fees** - Platform fees

### 🎯 Realistic Execution
- Position sizing
- Multiple cost models (volatility-based, volume-based)
- Market condition adjustments
- Asset class-specific costs

### 📊 Professional Metrics
- Returns (total, CAGR, annualized)
- Risk metrics (Sharpe, Sortino, max drawdown)
- Trade statistics (win rate, profit factor)
- Cost analysis (cost breakdown by type)

### 🔧 Production Ready
- Clean, extensible code
- Type hints throughout
- Comprehensive documentation
- Example strategies included

## 🚀 Quick Start

### Installation

```bash
cd backtesting_framework
pip install -r requirements.txt
```

### Run Example

```bash
cd examples
python naive_vs_realistic.py
```

This will show you the **shocking difference** between naive and realistic backtesting!

## 📖 Usage

### Basic Example

```python
from engine.backtest_engine import BacktestEngine
from costs.cost_model import get_cost_model
from metrics.performance_metrics import PerformanceMetrics
import pandas as pd

# Load your price data
data = pd.read_csv("price_data.csv")

# Choose a cost model
cost_model = get_cost_model("forex_retail")

# Initialize engine
engine = BacktestEngine(
    initial_capital=10000,
    cost_model=cost_model,
    position_size_pct=0.1  # 10% per trade
)

# Define your strategy
def my_strategy(data):
    # Your strategy logic here
    if some_condition:
        return "buy"
    elif other_condition:
        return "sell"
    return "hold"

# Run backtest
results = engine.run_backtest(data, my_strategy)

# Analyze performance
metrics = PerformanceMetrics(results)
metrics.print_summary()
```

### Available Cost Models

```python
from costs.cost_model import get_cost_model

# Preset models
models = {
    "forex_retail":         # Retail forex (2 bps spread)
    "forex_institutional":  # Institutional forex (0.5 bps)
    "stocks_commission_free": # Zero-commission stocks
    "stocks_traditional":   # Traditional broker
    "crypto_exchange":      # Crypto exchange (0.1% fee)
    "futures_cme":         # CME futures
}

cost_model = get_cost_model("forex_retail")
```

### Custom Cost Model

```python
from costs.cost_model import CostModel, AssetClass

custom_model = CostModel(
    asset_class=AssetClass.FOREX,
    spread_bps=1.5,              # 1.5 basis points spread
    commission_rate=0.0,         # No commission
    slippage_model="volatility", # Volatility-based slippage
    base_slippage_bps=0.3,       # 0.3 bps base slippage
    financing_rate_annual=0.04   # 4% annual financing
)
```

## 📁 Project Structure

```
backtesting_framework/
├── costs/
│   └── cost_model.py          # Cost modeling (spreads, slippage, etc.)
├── engine/
│   └── backtest_engine.py     # Core backtesting engine
├── metrics/
│   └── performance_metrics.py # Performance calculations
├── strategies/                # Example strategies
├── examples/
│   └── naive_vs_realistic.py  # Comparison example
├── requirements.txt
└── README.md
```

## 💡 Cost Model Details

### Spread Costs

The bid-ask spread you pay on every trade:

```python
# For a $1.0950 entry with 2 bps spread:
spread_cost = (2 / 10000) * 1.0950 * quantity
```

Can be adjusted for:
- Market volatility (wider spreads in volatile markets)
- Liquidity (wider spreads in illiquid markets)

### Slippage

Market impact and execution quality:

**Fixed Model:**
```python
slippage = base_slippage_bps * price * quantity
```

**Volume Model** (larger trades = more impact):
```python
slippage = base_slippage * (1 + 1/volume_ratio) * price * quantity
```

**Volatility Model** (volatile markets = more slippage):
```python
slippage = base_slippage * volatility_factor * price * quantity
```

### Commissions

Broker/exchange fees:

- **Forex**: Usually 0 (in spread) or per-lot
- **Stocks**: Per-share or percentage
- **Crypto**: Maker/taker fees (0.1-0.3%)
- **Futures**: Per-contract ($2-5)

### Financing Costs

Cost of holding positions overnight:

```python
daily_rate = annual_rate / 365
financing_cost = position_value * daily_rate * days_held
```

- **Longs**: Pay financing
- **Shorts**: May pay or receive (depends on asset)

## 📊 Performance Metrics

### Returns
- Total Return %
- CAGR (Compound Annual Growth Rate)
- Average daily/monthly/annual returns

### Risk-Adjusted
- **Sharpe Ratio**: Return per unit of risk
- **Sortino Ratio**: Return per unit of downside risk
- **Max Drawdown**: Largest peak-to-trough decline
- **Volatility**: Annualized standard deviation

### Trade Statistics
- Total trades
- Win rate %
- Profit factor (total wins / total losses)
- Average win/loss
- Largest win/loss
- Average holding period

### Cost Analysis
- Total costs
- Cost per trade
- Costs as % of gross P&L
- Breakdown by type (spread/slippage/commission)

## 🎓 Examples

### Example 1: Simple Moving Average

```python
def sma_crossover_strategy(data, fast=10, slow=30):
    """Buy on fast MA crossing above slow MA."""
    if len(data) < slow:
        return "hold"
    
    fast_ma = data["close"].rolling(fast).mean().iloc[-1]
    slow_ma = data["close"].rolling(slow).mean().iloc[-1]
    
    prev_fast = data["close"].rolling(fast).mean().iloc[-2]
    prev_slow = data["close"].rolling(slow).mean().iloc[-2]
    
    if prev_fast <= prev_slow and fast_ma > slow_ma:
        return "buy"
    elif prev_fast >= prev_slow and fast_ma < slow_ma:
        return "sell"
    
    return "hold"
```

### Example 2: RSI Strategy

```python
def rsi_strategy(data, period=14, oversold=30, overbought=70):
    """Buy when RSI < oversold, sell when > overbought."""
    if len(data) < period:
        return "hold"
    
    # Calculate RSI
    delta = data["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1]
    
    if current_rsi < oversold:
        return "buy"
    elif current_rsi > overbought:
        return "sell"
    
    return "hold"
```

## 🔧 Advanced Features

### Custom Market Conditions

```python
# Add market conditions to your data
data["volatility"] = data["close"].pct_change().rolling(20).std()
data["liquidity"] = data["volume"] / data["volume"].rolling(50).mean()
data["volume_ratio"] = your_trade_size / data["volume"]

# Costs will automatically adjust
```

### Position Sizing

```python
engine = BacktestEngine(
    initial_capital=10000,
    position_size_pct=0.1,  # 10% of capital
    max_positions=3          # Up to 3 concurrent positions
)
```

### Portfolio Backtesting

```python
# Test multiple assets simultaneously
for symbol in ["EURUSD", "GBPUSD", "USDJPY"]:
    data = load_data(symbol)
    results = engine.run_backtest(data, strategy)
    # Aggregate results...
```

## ⚠️ Common Mistakes to Avoid

1. **Using 100% of capital per trade** → Use 5-20% max
2. **Ignoring spread costs** → Major impact on short-term strategies
3. **Forgetting slippage** → Market orders always have slippage
4. **Not accounting for financing** → Overnight positions have costs
5. **Using unrealistic execution** → You won't always get exact prices

## 📈 Real-World Cost Examples

### High-Frequency Trading
```
Spread: 0.1 pips
Slippage: 0.5 pips
Commission: 0.2 pips
Per Trade Cost: 0.8 pips

If you trade 100 times/day:
Daily Cost: 80 pips
Monthly Cost: ~1,600 pips
```

### Swing Trading (Forex)
```
Spread: 2 pips
Slippage: 1 pip
Financing (5 days): 0.5 pips/day = 2.5 pips
Per Trade Cost: 5.5 pips

If you make 50 pips gross:
Net Profit: 44.5 pips (11% reduction)
```

### Stock Day Trading
```
Spread: $0.05/share
Slippage: $0.02/share
Commission: $0 (zero-commission)
Per Trade Cost: $7 on 100 shares

If you make $50 gross:
Net Profit: $43 (14% reduction)
```

## 🎯 Best Practices

1. **Always use realistic costs** matching your actual broker
2. **Test multiple scenarios** (low/medium/high cost environments)
3. **Account for market conditions** (volatile periods = higher costs)
4. **Include all cost types** (spread + slippage + commission + financing)
5. **Compare naive vs realistic** to see the true impact
6. **Track costs over time** to identify cost-efficient strategies

## 📝 Requirements

```
pandas>=1.5.0
numpy>=1.23.0
```

## 🤝 Contributing

To add new cost models or strategies:
1. Create new cost preset in `costs/cost_model.py`
2. Add example strategy to `strategies/`
3. Update README with usage example

## 📄 License

Free to use for personal and commercial purposes.

## 🎓 Learning Resources

### Understanding Trading Costs
- **Spread**: Price difference between bid and ask
- **Slippage**: Difference between expected and actual execution
- **Commission**: Flat fee per trade or percentage
- **Financing**: Cost/credit for overnight positions

### Why Costs Matter
A strategy with:
- 55% win rate
- 1:1 risk/reward
- 0 costs → +5% expected value per trade

Same strategy with 2 pips cost per trade:
- Might be -2% expected value per trade
- **Losing strategy!**

## 🚀 Next Steps

1. Run the naive vs realistic example
2. Test your own strategies with realistic costs
3. Compare different cost models
4. Optimize for cost efficiency
5. Deploy only strategies that survive realistic backtesting!

---

**Remember**: If your strategy doesn't work with realistic costs, it won't work in live trading. Period.
