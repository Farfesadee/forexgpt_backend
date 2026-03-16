
CREATE TABLE IF NOT EXISTS backtest_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy_type TEXT NOT NULL, -- 'sma', 'rsi', 'macd', 'bollinger', 'custom'
    strategy_code TEXT, -- Only populated for custom strategies
    currency_pair TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    capital FLOAT NOT NULL,
    position_size FLOAT NOT NULL,
    total_return FLOAT,
    sharpe_ratio FLOAT,
    max_drawdown FLOAT,
    win_rate FLOAT,
    total_trades INT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_backtest_results_user_id 
    ON backtest_results(user_id);

CREATE INDEX IF NOT EXISTS idx_backtest_results_strategy_type 
    ON backtest_results(strategy_type);

CREATE INDEX IF NOT EXISTS idx_backtest_results_created_at 
    ON backtest_results(created_at DESC);

-- Enable Row Level Security
ALTER TABLE backtest_results ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can view their own backtest results
CREATE POLICY "Users can view their own backtest results"
    ON backtest_results FOR SELECT
    USING (auth.uid() = user_id);

-- RLS Policy: Users can insert their own backtest results
CREATE POLICY "Users can insert their own backtest results"
    ON backtest_results FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- RLS Policy: Users can delete their own backtest results
CREATE POLICY "Users can delete their own backtest results"
    ON backtest_results FOR DELETE
    USING (auth.uid() = user_id);

-- Add comments for documentation
COMMENT ON TABLE backtest_results IS 'Stores results from strategy backtests, both built-in and custom user-generated strategies';
COMMENT ON COLUMN backtest_results.strategy_type IS 'Type of strategy: sma, rsi, macd, bollinger, or custom';
COMMENT ON COLUMN backtest_results.strategy_code IS 'Full Python code for custom strategies, NULL for built-in strategies';
COMMENT ON COLUMN backtest_results.total_return IS 'Total return percentage over the backtest period';
COMMENT ON COLUMN backtest_results.sharpe_ratio IS 'Annualized Sharpe ratio (risk-adjusted return)';
COMMENT ON COLUMN backtest_results.max_drawdown IS 'Maximum drawdown percentage during backtest';
COMMENT ON COLUMN backtest_results.win_rate IS 'Percentage of profitable trades';