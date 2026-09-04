# News-Based Trading Strategy

A Python project for news-driven trading strategy research, signal generation, and execution.

---

## 📁 Project Structure

```text
News_Based_Strategy/
├── .env                              # Local environment configuration (git-ignored)
├── .env.example                      # Template for environment variables
├── .gitignore                        # Git ignore rules for Python, cache, and secrets
├── pyproject.toml                    # Build configuration and dependencies
├── requirements.txt                  # Core requirements
├── README.md                         # Project documentation
├── data/
│   └── strategy.db                   # SQLite state database
├── src/
│   └── news_based_strategy/
│       ├── __init__.py               # Top-level package facade & exports
│       ├── config.py                 # Central settings & .env configuration
│       ├── engine.py                 # Strategy orchestrator loop
│       ├── main.py                   # CLI entry point
│       ├── core/                     # Shared data contracts & models
│       │   ├── __init__.py
│       │   └── models.py             # Announcement, FilingAudit, TradeSignal, TradeResult
│       ├── ingestion/                # Exchange feeds & text extraction
│       │   ├── __init__.py
│       │   ├── monitor.py            # NSE announcement poller & session manager
│       │   ├── universe.py           # Active F&O universe definitions
│       │   ├── filter.py             # Pre-LLM noise rejection engine
│       │   └── extractor.py          # In-memory PDF text extractor
│       ├── intelligence/             # AI reasoning & signal generation
│       │   ├── __init__.py
│       │   └── analyzer.py           # Gemini 2.5 Flash structured reasoning client
│       ├── storage/                  # State persistence & audit logging
│       │   ├── __init__.py
│       │   └── repository.py         # SQLite database repository
│       └── execution/                # Broker integration & risk management
│           ├── __init__.py
│           ├── risk.py               # Market hours gate & position sizing
│           └── executor.py           # DhanHQ order placement & dry-run simulator
└── tests/
    ├── __init__.py
    ├── test_core/                    # Models & schemas tests
    ├── test_ingestion/               # Feed, noise, universe & PDF tests
    ├── test_intelligence/            # AI analyzer & prompts tests
    ├── test_storage/                 # SQLite deduplication tests
    └── test_execution/               # Risk & order sizing tests
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10 or higher (Python 3.13 recommended)
- `venv` module for virtual environments

### 2. Environment Setup

Create and activate a virtual environment:

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS / Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
# Or install in editable mode with development dependencies:
pip install -e ".[dev]"
```

### 3. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Key variables configured in `.env`:
- `APP_ENV`: Application environment (`development`, `staging`, `production`)
- `LOG_LEVEL`: Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- `DHAN_CLIENT_ID`: Dhan broker Client ID
- `DHAN_ACCESS_TOKEN`: Dhan broker API access token
- `NEWS_API_KEY`: API key for news feeds / data sources

---

## 🧪 Running Tests

Run tests using Python's standard `unittest`:

```bash
python3 -m unittest discover -s tests -t .
```

Or using `pytest` (when installed):

```bash
pytest
```

---

## 🏃 Running the Poller

Start the real-time NSE corporate announcements poller:

```bash
# Default: Continuous polling every 60s for F&O stocks with noise filtering & PDF extraction
PYTHONPATH=src python3 -m news_based_strategy.main

# Custom interval (e.g. 30 seconds)
PYTHONPATH=src python3 -m news_based_strategy.main --interval 30

# Single shot test (poll once and exit)
PYTHONPATH=src python3 -m news_based_strategy.main --once

# Filter announcements for a specific symbol
PYTHONPATH=src python3 -m news_based_strategy.main --symbol TATAMOTORS

# Include all NSE stocks (disables F&O universe restriction)
PYTHONPATH=src python3 -m news_based_strategy.main --all-stocks

# Include compliance noise (trading window closures, share certificate intimations)
PYTHONPATH=src python3 -m news_based_strategy.main --include-noise

# Skip downloading/extracting PDF attachments
PYTHONPATH=src python3 -m news_based_strategy.main --no-pdf

# Skip dumping historical announcements on startup, only print new arrivals
PYTHONPATH=src python3 -m news_based_strategy.main --skip-initial
```
