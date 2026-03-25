"""
Data Fetcher for ForexGPT Backtesting
Fetches historical OHLCV data with automatic fallback across multiple sources.

Sources tried in order (when source="auto"):
1. Twelve Data   -- primary source, 800 req/day free, set TWELVE_DATA_KEY in .env
2. Alpha Vantage -- first fallback, 25 req/day free, set ALPHA_VANTAGE_KEY in .env
3. yfinance      -- second fallback, free, no API key needed
4. CSV file      -- fully offline fallback, place file at data/{SYMBOL}.csv

Usage:
    fetcher = DataFetcher()
    df = fetcher.fetch("EURUSD", "2020-01-01", "2024-01-01")

    # Force a specific source:
    df = fetcher.fetch("EURUSD", "2020-01-01", "2024-01-01", source="csv")
    df = fetcher.fetch("EURUSD", "2020-01-01", "2024-01-01", source="twelvedata")
"""

import os
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Multi-source historical data fetcher with automatic fallback.

    Sources (in order of priority):
    1. Twelve Data   -- primary, reliable, 800 req/day free tier
    2. Alpha Vantage -- first fallback, reliable, 25 req/day free tier
    3. yfinance      -- second fallback, free but unreliable for forex
    4. CSV file      -- offline fallback, no internet needed at all
    """

    # Twelve Data known pairs (others are auto-converted from EURUSD to EUR/USD)
    TWELVE_DATA_SYMBOL_MAP = {
        "EURUSD": "EUR/USD",
        "GBPUSD": "GBP/USD",
        "USDJPY": "USD/JPY",
        "AUDUSD": "AUD/USD",
        "USDCAD": "USD/CAD",
        "USDCHF": "USD/CHF",
        "NZDUSD": "NZD/USD",
        "EURGBP": "EUR/GBP",
        "EURJPY": "EUR/JPY",
    }

    # Yahoo Finance ticker format for forex pairs
    YFINANCE_SYMBOL_MAP = {
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
        "AUDUSD": "AUDUSD=X",
        "USDCAD": "USDCAD=X",
        "USDCHF": "USDCHF=X",
        "NZDUSD": "NZDUSD=X",
        "EURGBP": "EURGBP=X",
        "EURJPY": "EURJPY=X",
    }

    # Alpha Vantage uses separate from/to currency codes
    AV_SYMBOL_MAP = {
        "EURUSD": ("EUR", "USD"),
        "GBPUSD": ("GBP", "USD"),
        "USDJPY": ("USD", "JPY"),
        "AUDUSD": ("AUD", "USD"),
        "USDCAD": ("USD", "CAD"),
        "USDCHF": ("USD", "CHF"),
        "NZDUSD": ("NZD", "USD"),
        "EURGBP": ("EUR", "GBP"),
        "EURJPY": ("EUR", "JPY"),
    }

    def fetch(self, symbol, start, end, interval="1d", source="auto"):
        """
        Fetch OHLCV data for a symbol.

        Args:
            symbol:   Currency pair e.g. "EURUSD", "GBPUSD", "GBPJPY"
            start:    Start date "YYYY-MM-DD"
            end:      End date "YYYY-MM-DD"
            interval: "1d" (daily) or "1wk" (weekly)
            source:   "auto"         -- tries all sources in priority order
                      "twelvedata"   -- Twelve Data only
                      "alphavantage" -- Alpha Vantage only
                      "yfinance"     -- Yahoo Finance only
                      "csv"          -- local CSV file only

        Returns:
            DataFrame with columns: open, high, low, close, volume
            Index: DatetimeIndex
        """
        symbol = symbol.upper()

        if source == "auto":
            sources = ["twelvedata", "alphavantage", "yfinance", "csv"]
            last_error = None

            for src in sources:
                try:
                    logger.info(f"Trying data source: {src}")
                    df = self._fetch_from(src, symbol, start, end, interval)
                    if not df.empty:
                        logger.info(
                            f"Successfully fetched {len(df)} rows "
                            f"from {src} for {symbol}"
                        )
                        return df
                except Exception as e:
                    last_error = e
                    logger.warning(f"{src} failed: {e}. Trying next source...")

            raise ValueError(
                f"All data sources failed for '{symbol}'. "
                f"Last error: {last_error}\n"
                f"Options:\n"
                f"  - Add TWELVE_DATA_KEY to .env (get free key at twelvedata.com)\n"
                f"  - Add ALPHA_VANTAGE_KEY to .env (get free key at alphavantage.co)\n"
                f"  - Check your internet connection for yfinance\n"
                f"  - Place data/{symbol}.csv for offline use"
            )
        else:
            return self._fetch_from(source, symbol, start, end, interval)

    def _fetch_from(self, source, symbol, start, end, interval):
        """Route to the correct source."""
        if source == "twelvedata":
            return self._from_twelvedata(symbol, start, end, interval)
        elif source == "alphavantage":
            return self._from_alphavantage(symbol, start, end)
        elif source == "yfinance":
            return self._from_yfinance(symbol, start, end, interval)
        elif source == "csv":
            return self._from_csv(symbol, start, end)
        else:
            raise ValueError(
                f"Unknown source '{source}'. "
                f"Use: auto, twelvedata, alphavantage, yfinance, csv"
            )

    # =========================================================================
    # SOURCE 1: Twelve Data (primary)
    # =========================================================================

    def _from_twelvedata(self, symbol, start, end, interval):
        """
        Fetch from Twelve Data (primary source).
        Free tier: 800 requests/day, 8 requests/minute.

        Supports any valid 6-character forex pair automatically.
        Known pairs use the symbol map; others are auto-converted
        e.g. GBPJPY becomes GBP/JPY automatically.

        Setup:
            Add to .env: TWELVE_DATA_KEY=your_key_here
            Get free key at: https://twelvedata.com
        """
        import requests

        api_key = os.getenv("TWELVE_DATA_KEY")
        if not api_key:
            raise ValueError(
                "TWELVE_DATA_KEY not found in .env. "
                "Get a free key at: https://twelvedata.com"
            )

        # Known pairs use the map; any other 6-char pair is auto-converted
        if symbol in self.TWELVE_DATA_SYMBOL_MAP:
            td_symbol = self.TWELVE_DATA_SYMBOL_MAP[symbol]
        elif len(symbol) == 6:
            td_symbol = f"{symbol[:3]}/{symbol[3:]}"
        else:
            raise ValueError(
                f"Cannot convert '{symbol}' to Twelve Data format. "
                f"Use standard 6-character forex pairs e.g. EURUSD, GBPJPY."
            )

        interval_map = {"1d": "1day", "1wk": "1week"}
        td_interval = interval_map.get(interval, "1day")

        url = (
            f"https://api.twelvedata.com/time_series"
            f"?symbol={td_symbol}"
            f"&interval={td_interval}"
            f"&start_date={start}"
            f"&end_date={end}"
            f"&outputsize=5000"
            f"&order=ASC"
            f"&apikey={api_key}"
        )

        logger.info(f"Twelve Data: fetching {symbol} ({td_symbol})")
        response = requests.get(url, timeout=30)
        data = response.json()

        if data.get("status") == "error":
            raise ValueError(
                f"Twelve Data error: {data.get('message', 'Unknown error')}"
            )

        if "values" not in data:
            raise ValueError(
                f"Twelve Data returned unexpected response for '{symbol}': "
                f"{data.get('message', str(data))}"
            )

        values = data["values"]
        if not values:
            raise ValueError(
                f"Twelve Data returned no data for '{symbol}' "
                f"in range {start} to {end}."
            )

        records = []
        for row in values:
            records.append({
                "date":   pd.to_datetime(row["datetime"]),
                "open":   float(row["open"]),
                "high":   float(row["high"]),
                "low":    float(row["low"]),
                "close":  float(row["close"]),
                "volume": float(row.get("volume", 0)),
            })

        df = pd.DataFrame(records).set_index("date").sort_index()

        if df.empty:
            raise ValueError(
                f"Twelve Data returned empty DataFrame for '{symbol}'."
            )

        logger.info(f"Twelve Data: got {len(df)} rows for {symbol}")
        return df[["open", "high", "low", "close", "volume"]]

    # =========================================================================
    # SOURCE 2: Alpha Vantage (first fallback)
    # =========================================================================

    def _from_alphavantage(self, symbol, start, end):
        """
        Fetch from Alpha Vantage (first fallback).
        Free tier: 25 requests/day, 5 requests/minute.
        Limited to 9 hardcoded pairs in AV_SYMBOL_MAP.

        Setup:
            Add to .env: ALPHA_VANTAGE_KEY=your_key_here
            Get free key at: https://www.alphavantage.co/support/#api-key
        """
        import requests

        api_key = os.getenv("ALPHA_VANTAGE_KEY")
        if not api_key:
            raise ValueError(
                "ALPHA_VANTAGE_KEY not found in .env. "
                "Get a free key at: https://www.alphavantage.co/support/#api-key"
            )

        if symbol not in self.AV_SYMBOL_MAP:
            raise ValueError(
                f"'{symbol}' not supported by Alpha Vantage fetcher. "
                f"Supported: {list(self.AV_SYMBOL_MAP.keys())}"
            )

        from_currency, to_currency = self.AV_SYMBOL_MAP[symbol]
        url = (
            f"https://www.alphavantage.co/query"
            f"?function=FX_DAILY"
            f"&from_symbol={from_currency}"
            f"&to_symbol={to_currency}"
            f"&outputsize=full"
            f"&apikey={api_key}"
        )

        logger.info(f"Alpha Vantage: fetching {symbol} ({from_currency}/{to_currency})")
        response = requests.get(url, timeout=30)
        data = response.json()

        if "Time Series FX (Daily)" not in data:
            error = data.get("Note") or data.get("Information") or str(data)
            raise ValueError(f"Alpha Vantage error: {error}")

        ts = data["Time Series FX (Daily)"]
        records = []
        for date_str, values in ts.items():
            records.append({
                "date":   pd.to_datetime(date_str),
                "open":   float(values["1. open"]),
                "high":   float(values["2. high"]),
                "low":    float(values["3. low"]),
                "close":  float(values["4. close"]),
                "volume": 0.0,
            })

        df = pd.DataFrame(records).set_index("date").sort_index()
        df = df[
            (df.index >= pd.to_datetime(start)) &
            (df.index <= pd.to_datetime(end))
        ]

        if df.empty:
            raise ValueError(
                f"Alpha Vantage returned no data for '{symbol}' "
                f"in range {start} to {end}."
            )

        logger.info(f"Alpha Vantage: got {len(df)} rows for {symbol}")
        return df[["open", "high", "low", "close", "volume"]]

    # =========================================================================
    # SOURCE 3: yfinance (second fallback)
    # =========================================================================

    def _from_yfinance(self, symbol, start, end, interval):
        """
        Fetch from Yahoo Finance (second fallback).
        Free, no API key needed. Unreliable for forex.
        Limited to 9 hardcoded pairs in YFINANCE_SYMBOL_MAP.
        """
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("Run: pip install yfinance")

        ticker = self.YFINANCE_SYMBOL_MAP.get(symbol, symbol)
        logger.info(f"yfinance: downloading {ticker}")

        df = yf.download(
            ticker,
            start=start,
            end=end,
            interval=interval,
            progress=False,
            auto_adjust=True,
            group_by="ticker"
        )

        if df.empty:
            raise ValueError(
                f"yfinance returned no data for '{symbol}' ({ticker}). "
                f"Check the symbol and date range."
            )

        if isinstance(df.columns, pd.MultiIndex):
            fields = {"open", "high", "low", "close", "volume", "adj close"}
            sample = df.columns[0][0].lower()
            if sample in fields:
                df.columns = [col[0].lower() for col in df.columns]
            else:
                df.columns = [col[1].lower() for col in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        if "volume" not in df.columns:
            df["volume"] = 0.0

        df = df[["open", "high", "low", "close", "volume"]].copy()
        df.dropna(inplace=True)
        return df

    # =========================================================================
    # SOURCE 4: CSV (fully offline fallback)
    # =========================================================================

    def _from_csv(self, symbol, start, end):
        """
        Load data from a local CSV file. Fully offline.

        Setup:
            Place file at data/{SYMBOL}.csv e.g. data/EURUSD.csv
            Required columns: date, open, high, low, close
            Optional: volume (defaults to 0 if missing)

        Where to get free historical forex CSVs:
            https://www.histdata.com/download-free-forex-historical-data/
        """
        csv_path = os.path.join("data", f"{symbol}.csv")

        if not os.path.exists(csv_path):
            raise FileNotFoundError(
                f"CSV file not found at '{csv_path}'.\n"
                f"Download from histdata.com and name it data/{symbol}.csv"
            )

        logger.info(f"CSV: loading {csv_path}")
        df = pd.read_csv(csv_path)
        date_col = "Date" if "Date" in df.columns else "date"
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.set_index(date_col)
        df.index.name = "date"
        df.columns = [c.lower() for c in df.columns]

        df = df[
            (df.index >= pd.to_datetime(start)) &
            (df.index <= pd.to_datetime(end))
        ]

        if df.empty:
            raise ValueError(
                f"CSV '{csv_path}' has no data between {start} and {end}."
            )

        for col in ["open", "high", "low", "close"]:
            if col not in df.columns:
                raise ValueError(
                    f"CSV '{csv_path}' is missing required column: '{col}'"
                )

        if "volume" not in df.columns:
            df["volume"] = 0.0

        logger.info(f"CSV: loaded {len(df)} rows for {symbol}")
        return df[["open", "high", "low", "close", "volume"]]

    # =========================================================================
    # NORMALIZER
    # =========================================================================

    def _normalize(self, df):
        """Normalize column names to lowercase and keep only OHLCV."""
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0].lower() for col in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        df = df[["open", "high", "low", "close", "volume"]].copy()
        df.dropna(inplace=True)
        return df
