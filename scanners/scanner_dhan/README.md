# Scanner on Dhan (`scanner_dhan`)

`scanner_dhan` is a modular, high-performance Python framework for building, running, and backtesting multi-market technical scanners with **DhanHQ API** integration.

## Project Layout

```text
Scanner_On_Dhan/
├── src/scanner_dhan/
│   ├── config.py                 # Backtest & simulation configuration
│   ├── models.py                 # Core domain models (Bar, Signal, SignalType)
│   ├── data/                     # [COMMON] Data sources & DhanHQ adapters
│   │   ├── base.py               # MarketDataSource protocol
│   │   └── dhan_provider.py      # DhanHQ historical & batch LTP provider
│   ├── universe/                 # [COMMON] Reusable stock universes & resolvers
│   │   └── nifty50.py            # Nifty 50 constituents & Dhan security IDs
│   ├── indicators/               # [COMMON] Reusable indicators & math
│   │   ├── moving_averages.py    # EMA, SMA calculations
│   │   ├── pivots.py             # Floor/Classic Pivots (S1, S2, R1, R2)
│   │   ├── rsi.py                # Wilder's 14-period RSI
│   │   └── candlesticks.py       # Hammer, Shooting Star, Engulfing patterns
│   ├── scanner/                  # [FRAMEWORK] Core scanner registry & engines
│   │   ├── base.py               # BaseScanner, ScannerParameter, ScanReport
│   │   ├── registry.py           # ScannerRegistry, @register_scanner decorator
│   │   └── nifty50_support_resistance/ # [DEDICATED SCANNER PACKAGE]
│   │       ├── models.py         # SupportLevel, SupportType, StockSupportScan
│   │       ├── level_detector.py # Fractal swing detection & zone clustering
│   │       └── scanners.py       # Support, Resistance, RSI Extremes scanners
│   ├── execution/                # [COMMON] Portfolio backtest engine
│   ├── metrics/                  # [COMMON] Returns & Drawdown metrics
│   ├── strategies/               # [COMMON] Strategy contracts
│   └── ui/                       # [COMMON] FastAPI backend & Web Dashboard
├── examples/                     # Runnable CLI scanner examples
├── tests/                        # Unit tests parallel to the source package
├── run_dashboard.py              # Web dashboard launcher
└── pyproject.toml
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,dhan]"
pytest
```

## Running the Web Dashboard

```bash
python run_dashboard.py
```

## Running the CLI Scanner

```bash
python examples/nifty50_support_scanner.py --threshold 2.0
```
