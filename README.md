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
├── deploy.sh                          # 🚀 One-command deploy shortcut to GCP
│
├── infra/                             # 🌐 Platform Infrastructure & DevOps
│   ├── terraform/                     # ☁️ GCP Infrastructure IaC (VM, VPC, Firewall, IP)
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── terraform_common.tfvars
│   │   └── terraform.tfvars
│   │
│   ├── docker/                        # 🐳 Containerization definitions
│   │   ├── Dockerfile                 # Unified multi-package container
│   │   └── docker-compose.yml
│   │
│   └── deploy/                        # 🛠️ Operational & Deployment Scripts
│       ├── deploy.sh                  # Full Terraform provisioning + deployment
│       ├── deploy_code.sh             # Fast code-only deployment to GCP VM
│       └── docker.sh                  # Local container management (up, down, logs)
│
├── scanners/
│   └── scanner_dhan/                  # 📊 Shared Scanner Library & Universe Manager
│       ├── src/scanner_dhan/
│       ├── tests/
│       └── pyproject.toml
│
└── strategies/
    ├── news_based_strategy/           # 📰 Real-Time NSE Catalyst Equity Strategy
    │   ├── src/news_based_strategy/
    │   ├── tests/
    │   └── pyproject.toml
    │
    └── st14_bullish_ce/               # 🚀 Bullish 1-OTM Call Options Strategy
        ├── src/st14_bullish_ce/
        ├── tests/
        └── pyproject.toml
```

---

## 📊 Strategy Portfolio Inventory

| Strategy Name | Directory | Type / Style | Port | Status | Documentation |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **`news_based_strategy`** | [`strategies/news_based_strategy`](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/strategies/news_based_strategy) | Intraday Event-Driven (AI Catalyst) | `8000` | 🟢 Active | [Docs](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/strategies/news_based_strategy/readme/README.md) |
| **`st14_bullish_ce`** | [`strategies/st14_bullish_ce`](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/strategies/st14_bullish_ce) | Intraday Bullish 1-OTM Options | Integrated (`8000`) | 🟢 Active | [Source](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/strategies/st14_bullish_ce) |

---

## 🚀 Quick Execution Guide

### 🐳 Docker & Local Operations
* **Start Container Locally**:
  ```bash
  ./infra/deploy/docker.sh up -d
  ```
* **View Live Container Logs**:
  ```bash
  ./infra/deploy/docker.sh logs
  ```
* **Stop Container**:
  ```bash
  ./infra/deploy/docker.sh down
  ```

### ☁️ GCP Cloud Deployment
* **Fast Code-Only Deploy to GCP VM**:
  ```bash
  ./deploy.sh
  # or: ./infra/deploy/deploy_code.sh
  ```
* **Full Terraform IaC Provision & Deploy**:
  ```bash
  ./infra/deploy/deploy.sh
  ```

---

## 🛠️ Adding a New Strategy

To scaffold a new strategy (e.g. `my_new_strategy`) in this monorepo:

1. **Create strategy root and subdirectories**:
   ```bash
   mkdir -p strategies/my_new_strategy/{src/my_new_strategy,tests,data,infra/{docker,gcp,scripts},readme}
   ```
2. **Assign a unique host port** in `docker-compose.yml` and `config.py`.
3. **Configure isolated GCP remote target directory** in `infra/scripts/deploy_code.sh`.
4. **Create strategy documentation** inside `strategies/my_new_strategy/readme/`.
5. **Register the strategy** in this root [README.md](file:///Users/amitdatta/Amit_Work/Trading_Work/Strategy_NSE_NEWS/strategy_dhan_nse_news/README.md).

---

## 🧪 Running Monorepo Tests

Run unit tests across all strategies from the repository root:

```bash
# Test Scanner Dhan Library
PYTHONPATH="scanners/scanner_dhan/src:scanners/scanner_dhan" /opt/anaconda3/bin/python -m pytest scanners/scanner_dhan/tests

# Test ST-14 Bullish CE Options Strategy
PYTHONPATH="scanners/scanner_dhan/src:strategies/st14_bullish_ce/src" /opt/anaconda3/bin/python -m pytest strategies/st14_bullish_ce/tests

# Test News-Based Strategy
PYTHONPATH="scanners/scanner_dhan/src:strategies/st14_bullish_ce/src:strategies/news_based_strategy/src" /opt/anaconda3/bin/python -m pytest strategies/news_based_strategy/tests
```
