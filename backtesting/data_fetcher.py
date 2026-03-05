"""
Data Fetcher for ForexGPT Backtesting
Fetches historical OHLCV data with automatic fallback across multiple sources.

Sources tried in order (when source="auto"):
1. yfinance      — free, no API key needed (default)
2. Alpha Vantage — free API key required, set ALPHA_VANTAGE_KEY in .env
3. CSV file      — fully offline fallback, place file at data/{SYMBOL}.csv

Usage:
    fetcher = DataFetcher()
    df = fetcher.fetch("EURUSD", "2020-01-01", "2024-01-01")

    # Force a specific source:
    df = fetcher.fetch("EURUSD", "2020-01-01", "2024-01-01", source="csv")
"""

import os
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Multi-source historical data fetcher with automatic fallback.

    Sources:
    1. yfinance      — default, free, no setup needed
    2. Alpha Vantage — fallback if yfinance fails, needs free API key
    3. CSV file      — offline fallback, no internet needed at all
    """

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

    def fetch(
        self,
        symbol: str,
        start: str,
        end: str,
        interval: str = "1d",
        source: str = "auto"
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for a symbol.

        Args:
            symbol:   Currency pair e.g. "EURUSD", "GBPUSD"
            start:    Start date "YYYY-MM-DD"
            end:      End date "YYYY-MM-DD"
            interval: "1d" (daily) or "1wk" (weekly)
            source:   "auto"        — tries all sources in order
                      "yfinance"    — Yahoo Finance only
                      "alphavantage"— Alpha Vantage only
                      "csv"         — local CSV file only

        Returns:
            DataFrame with columns: open, high, low, close, volume
            Index: DatetimeIndex
        """
        symbol = symbol.upper()

        if source == "auto":
            # Try each source in order, fall back on failure
            sources = ["yfinance", "alphavantage", "csv"]
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
                f"  - Check your internet connection for yfinance\n"
                f"  - Add ALPHA_VANTAGE_KEY to .env for Alpha Vantage\n"
                f"  - Place data/{symbol}.csv for offline use"
            )
        else:
            return self._fetch_from(source, symbol, start, end, interval)

    def _fetch_from(
        self, source: str, symbol: str,
        start: str, end: str, interval: str
    ) -> pd.DataFrame:
        """Route to the correct source."""
        if source == "yfinance":
            return self._from_yfinance(symbol, start, end, interval)
        elif source == "alphavantage":
            return self._from_alphavantage(symbol, start, end)
        elif source == "csv":
            return self._from_csv(symbol, start, end)
        else:
            raise ValueError(
                f"Unknown source '{source}'. "
                f"Use: auto, yfinance, alphavantage, csv"
            )

    # =========================================================================
    # SOURCE 1: yfinance (default)
    # =========================================================================

    def _from_yfinance(
        self, symbol: str, start: str, end: str, interval: str
    ) -> pd.DataFrame:
        """
        Fetch from Yahoo Finance.
        Free, no API key needed. Works for all major forex pairs.
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
            auto_adjust=True
        )

        if df.empty:
            raise ValueError(
                f"yfinance returned no data for '{symbol}' ({ticker}). "
                f"Check the symbol and date range."
            )

        # yfinance returns MultiIndex columns: ('Close', 'EURUSD=X')
        # Flatten to just the field name in lowercase: 'close'
        if isinstance(df.columns, __import__('pandas').MultiIndex):
            df.columns = [col[0].lower() for col in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        # Ensure volume column exists (forex returns 0s)
        if "volume" not in df.columns:
            df["volume"] = 0.0

        df = df[["open", "high", "low", "close", "volume"]].copy()
        df.dropna(inplace=True)
        return df

    # =========================================================================
    # SOURCE 2: Alpha Vantage (fallback)
    # =========================================================================

    def _from_alphavantage(
        self, symbol: str, start: str, end: str
    ) -> pd.DataFrame:
        """
        Fetch from Alpha Vantage (free tier, daily data only).

        Setup:
        1. Go to https://www.alphavantage.co/support/#api-key
        2. Sign up for a free API key
        3. Add to your .env file: ALPHA_VANTAGE_KEY=your_key_here

        Note: Free tier is limited to 25 requests/day and 5/minute.
        """
        try:
            import requests
        except ImportError:
            raise ImportError("Run: pip install requests")

        api_key = os.getenv("ALPHA_VANTAGE_KEY")
        if not api_key:
            raise ValueError(
                "ALPHA_VANTAGE_KEY not found in .env. "
                "Get a free key at: https://www.alphavantage.co/support/#api-key "
                "Then add to .env: ALPHA_VANTAGE_KEY=your_key"
            )

        if symbol not in self.AV_SYMBOL_MAP:
            raise ValueError(
                f"'{symbol}' not supported by Alpha Vantage fetcher. "
                f"Supported: {list(self.AV_SYMBOL_MAP.keys())}"
            )

        from_currency, to_currency = self.AV_SYMBOL_MAP[symbol]
        url = (
            "https://www.alphavantage.co/query"
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
                "volume": 0.0   # AV forex does not provide volume
            })

        df = pd.DataFrame(records).set_index("date").sort_index()

        # Filter to requested date range
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
    # SOURCE 3: CSV (fully offline fallback)
    # =========================================================================

    def _from_csv(
        self, symbol: str, start: str, end: str
    ) -> pd.DataFrame:
        """
        Load data from a local CSV file. Fully offline — no internet needed.

        Setup:
        1. Create a folder called 'data' in your project root
        2. Place your CSV file there named exactly: EURUSD.csv, GBPUSD.csv etc.

        Required CSV columns:
            date, open, high, low, close
        Optional:
            volume (will default to 0 if missing)

        CSV example:
            date,open,high,low,close,volume
            2020-01-02,1.12010,1.12150,1.11980,1.12100,0
            2020-01-03,1.12100,1.12300,1.11900,1.12050,0

        Where to get free historical forex CSVs:
        - https://www.histdata.com/download-free-forex-historical-data/
        - https://forexsb.com/historical-forex-data
        """
        csv_path = os.path.join("data", f"{symbol}.csv")

        if not os.path.exists(csv_path):
            raise FileNotFoundError(
                f"CSV file not found at '{csv_path}'.\n"
                f"To use offline mode:\n"
                f"  1. Create a 'data/' folder in your project\n"
                f"  2. Download {symbol} CSV from histdata.com\n"
                f"  3. Name it exactly: data/{symbol}.csv\n"
                f"  4. Ensure columns: date, open, high, low, close"
            )

        logger.info(f"CSV: loading {csv_path}")
        df = pd.read_csv(csv_path, parse_dates=["date"], index_col="date")
        df.columns = [c.lower() for c in df.columns]

        # Filter by date range
        df = df[
            (df.index >= pd.to_datetime(start)) &
            (df.index <= pd.to_datetime(end))
        ]

        if df.empty:
            raise ValueError(
                f"CSV '{csv_path}' has no data between {start} and {end}."
            )

        # Validate required columns
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

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names to lowercase and keep only OHLCV."""
        # Handle multi-level columns from yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0].lower() for col in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        df = df[["open", "high", "low", "close", "volume"]].copy()
        df.dropna(inplace=True)
        return df
