# ☁️ ST15_LargeCap — GCP Deployment Guide

This guide covers deploying the **ST15_LargeCap Positional Momentum Strategy** onto Google Cloud Compute Engine.

---

## ⚡ Fast Code Deployment (`deploy_code.sh`)

Push local code updates and rebuild the Docker container on port `8015`:

```bash
cd strategies/st15_largecap
./infra/scripts/deploy_code.sh
```

---

## 🛠️ Remote Host Setup
* The deployment script packages the strategy code into `/opt/st15_largecap` on the VM.
* Container runs on host port `8015` in parallel with `news_based_strategy` (port `8000`) without collision.

