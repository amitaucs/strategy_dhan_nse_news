# ⚡ Multi-Strategy Quantitative Trading Monorepo

A modular, independently deployable multi-strategy algorithmic trading workspace for Indian capital markets (**NSE & DhanHQ Broker**).

---

## 🏛️ Architectural Principles

This repository is structured as a **Decoupled Strategy Monorepo** where every trading strategy exists as an independent, self-contained package under the `strategies/` directory.

### Core Tenets:
1. **Zero Cross-Strategy Coupling**: Strategies do not import from or depend on each other. Each strategy has its own dependencies, models, and execution logic.
2. **Isolated Runtime & Data**: Each strategy maintains its own isolated database (`data/`), cache files, logs, and state. Resetting or wiping one strategy has **zero impact** on others.
3. **Dedicated Port Allocation**: Every strategy runs its Web UI / API on a dedicated, non-overlapping port (e.g., `8000`, `8015`).
4. **Independent Deployment**: Each strategy has its own Dockerfile, Compose file, Terraform configuration, and deployment scripts (`infra/scripts/`). A strategy can be built, updated, or restarted in production without affecting other running strategies.

---

## 📁 Monorepo Layout Specification

```text
strategy_dhan_nse_news/
├── infra/                         # 🌐 Shared Base Platform Infrastructure
│   └── terraform/                 # Single Source of Truth for GCP Host VM
│       ├── terraform_common.tfvars.example
│       ├── terraform_common.tfvars
│       └── README.md
│
├── strategies/
│   └── <strategy_name>/
│       ├── src/                   # 🐍 Python application package
│       │   └── <strategy_name>/
│       │       ├── __init__.py    # Public package interface & version
│       │       ├── config.py      # Environment configuration loader
│       │       └── main.py        # CLI & Web server entry points
│
├── tests/                         # 🧪 Strategy-specific test suite
│   ├── __init__.py
│   └── test_*.py
│
├── data/                          # 🗄️ Isolated runtime storage (DBs, caches, JSON files)
│
├── infra/                         # 🏗️ Infrastructure & Containerization
│   ├── docker/                    # Dockerfile & docker-compose.yml
│   ├── gcp/                       # Terraform IaC (main.tf, variables.tf, outputs.tf)
│   └── scripts/                   # Dedicated operational shell scripts
│       ├── docker.sh              # Local/server Docker management
│       ├── deploy_code.sh         # Fast GCP VM code deployment
│       └── deploy.sh              # Full Terraform infrastructure provisioner
│
├── readme/                        # 📑 Strategy Documentation Hub
│   ├── README.md                  # Main strategy overview, logic & configuration
│   ├── README_DOCKER.md           # Docker usage, port mapping & container logs
│   └── README_GCP.md              # Cloud architecture, scheduling & VM monitoring
│
├── .env.example                   # Environment variable template
├── pyproject.toml                 # Build system & package dependencies
└── requirements.txt               # Pinned pip dependencies
```

---

## 📊 Strategy Portfolio Inventory

| Strategy Name | Directory | Type / Style | Port | Status | Documentation |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **`news_based_strategy`** | [`strategies/news_based_strategy`](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/strategies/news_based_strategy) | Intraday Event-Driven (AI Catalyst) | `8000` | 🟢 Active | [Docs](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/strategies/news_based_strategy/readme/README.md) |
| **`st15_largecap`** | [`strategies/st15_largecap`](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/strategies/st15_largecap) | Positional Momentum (Nifty 50/100) | `8015` | 🔵 Scaffold | [Docs](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/strategies/st15_largecap/readme/README.md) |

---

## 🚀 Quick Execution Guide

### 🟢 Strategy 1: `news_based_strategy` (Port 8000)
* **Local Run**:
  ```bash
  cd strategies/news_based_strategy
  python3 -m news_based_strategy.main --gui --port 8000
  ```
* **Docker Run**:
  ```bash
  cd strategies/news_based_strategy
  ./infra/scripts/docker.sh up -d
  ```
* **Deploy to GCP**:
  ```bash
  cd strategies/news_based_strategy
  ./infra/scripts/deploy_code.sh
  ```

---

### 🔵 Strategy 2: `st15_largecap` (Port 8015)
* **Local Run**:
  ```bash
  cd strategies/st15_largecap
  python3 -m st15_largecap.main --gui --port 8015
  ```
* **Docker Run**:
  ```bash
  cd strategies/st15_largecap
  ./infra/scripts/docker.sh up -d
  ```
* **Deploy to GCP**:
  ```bash
  cd strategies/st15_largecap
  ./infra/scripts/deploy_code.sh
  ```

---

## 🛠️ Adding a New Strategy

To scaffold a new strategy (e.g. `my_new_strategy`) in this monorepo:

1. **Create strategy root and subdirectories**:
   ```bash
   mkdir -p strategies/my_new_strategy/{src/my_new_strategy,tests,data,infra/{docker,gcp,scripts},readme}
   ```
2. **Assign a unique host port** (e.g., `8020`) in `docker-compose.yml` and `config.py`.
3. **Configure isolated GCP remote target directory** (e.g., `/opt/my_new_strategy`) in `infra/scripts/deploy_code.sh`.
4. **Create strategy documentation** inside `strategies/my_new_strategy/readme/`.
5. **Register the strategy** in this root [README.md](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/README.md).

---

## 🧪 Running Monorepo Tests

Run unit tests across all strategies from the repository root:

```bash
# Test News-Based Strategy
PYTHONPATH=strategies/news_based_strategy/src python3 -m unittest discover -s strategies/news_based_strategy/tests -t .

# Test ST15 LargeCap Strategy
PYTHONPATH=strategies/st15_largecap/src python3 -m unittest discover -s strategies/st15_largecap/tests -t .
```
