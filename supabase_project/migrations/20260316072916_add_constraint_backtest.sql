
ALTER TABLE backtest_trades 
ADD CONSTRAINT backtest_trades_side_check 
CHECK (side IN ('buy', 'sell', 'BUY', 'SELL', 'long', 'short'));

-- Note: Adding a constraint is basically setting a "rule" that the database must follow. It prevents "bad" data from being saved, ensuring your tables stay clean and organized.
-- In Supabase (which uses PostgreSQL), constraints are like the ultimate guardrails for your data.