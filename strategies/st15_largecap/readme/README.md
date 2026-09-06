# 🔵 ST15_LargeCap — Positional Momentum Strategy

A modular, independently deployable **Positional Momentum Strategy** for Indian Large-Cap Equities (Nifty 50 / Nifty 100) using DhanHQ execution.

---

## 📑 Documentation Index

| Document | Description |
| :--- | :--- |
| **[README.md](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/strategies/st15_largecap/readme/README.md)** | Main strategy overview, configuration scaffold & parameters |
| **[README_DOCKER.md](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/strategies/st15_largecap/readme/README_DOCKER.md)** | Container architecture & port 8015 configuration |
| **[README_GCP.md](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/strategies/st15_largecap/readme/README_GCP.md)** | GCP VM deployment & Terraform integration |

---

## 📁 Package Structure

```
strategies/st15_largecap/
├── src/
│   └── st15_largecap/
│       ├── __init__.py
│       ├── config.py            # Dataclass settings loader
│       └── main.py              # Application entry point
├── tests/
│   ├── __init__.py
│   └── test_basic.py
├── infra/
│   ├── docker/
│   │   ├── Dockerfile
│   │   └── docker-compose.yml   # Port 8015
│   ├── gcp/
│   │   ├── main.tf
│   │   ├── outputs.tf
│   │   ├── variables.tf
│   │   └── terraform.tfvars.example
│   └── scripts/
│       ├── docker.sh
│       └── deploy_code.sh
├── readme/
│   ├── README.md
│   ├── README_DOCKER.md
│   └── README_GCP.md
├── .env.example
├── pyproject.toml
└── requirements.txt
```

---

## 🚀 Quick Start

### 1. Local Execution
```bash
cd strategies/st15_largecap
pip install -r requirements.txt

# Run Web UI Dashboard on Port 8015
python3 -m st15_largecap.main --gui --port 8015
```

### 2. Docker Execution
```bash
./infra/scripts/docker.sh up -d --build
./infra/scripts/docker.sh logs
./infra/scripts/docker.sh down
```

### 3. GCP Code Deployment
```bash
./infra/scripts/deploy_code.sh
```

---

## ⚙️ Strategy Parameters (`.env`)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `UNIVERSE_TYPE` | `NIFTY_100` | Equity universe (`NIFTY_50` or `NIFTY_100`) |
| `MAX_POSITIONS` | `5` | Maximum concurrent positional holdings |
| `CAPITAL_PER_POSITION` | `50000.0` | Allocated INR capital per stock |
| `TARGET_PROFIT_PCT` | `12.0` | Target profit threshold (%) |
| `STOP_LOSS_PCT` | `4.0` | Stop loss threshold (%) |
| `TRAILING_SL_PCT` | `3.0` | Trailing stop loss threshold (%) |
| `DRY_RUN` | `true` | Paper trading mode |
| `AUTO_ORDER` | `false` | Automatic execution toggle |
| `PORT` | `8015` | Web dashboard port |

