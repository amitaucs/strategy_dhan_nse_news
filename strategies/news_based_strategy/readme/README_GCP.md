# ☁️ Google Cloud Platform (GCP) Infrastructure & Deployment Guide

This guide covers provisioning and deploying the **NSE Catalyst Trading Terminal** (`news_based_strategy`) onto Google Cloud Compute Engine using Terraform and bash automation.

---

## 🏛️ Infrastructure Architecture

- **Default Setting (Option 1 - Always Free Tier)**:
  - **Region**: `us-central1` (Iowa) / `us-central1-a`
  - **Machine Type**: `e2-micro` (2 vCPUs shared, 1 GB RAM + 2 GB swapfile)
  - **Disk**: 30 GB standard persistent disk (`pd-standard`)
  - **Monthly Cost**: **₹0 / month (100% Free Forever under GCP Always Free Tier)**
- **Low-Latency Setting (Option 2 - Mumbai)**:
  - **Region**: `asia-south1` (Mumbai) / `asia-south1-a`
  - Switchable by modifying `infra/gcp/terraform.tfvars`.
- **Static External IP**: Dedicated static public IP so DNS / Web UI URL never changes across restarts.
- **Automated Startup Script**: Automatically configures a 2 GB swapfile, installs Docker Engine, and sets up working directories.
- **Firewall Rules**: Automatically allows inbound traffic on port `8000` (Web UI) and port `22` (SSH).

---

## ⚡ Deployment Workflows

### Option A: Fast Code Deployment (`deploy_code.sh`)
When infrastructure is already provisioned, push local code changes and rebuild the Docker container in seconds:
```bash
cd strategies/news_based_strategy
./infra/scripts/deploy_code.sh
```

### Option B: Full Infrastructure Provisioning (`deploy.sh`)
To provision infrastructure from scratch with Terraform and launch the terminal:
```bash
cd strategies/news_based_strategy

# 1. Prepare configuration
cp infra/gcp/terraform.tfvars.example infra/gcp/terraform.tfvars
# (Edit infra/gcp/terraform.tfvars with your GCP project_id)

# 2. Run automated deploy
./infra/scripts/deploy.sh
```

---

## 📊 Live Remote Telemetry & Log Monitoring

Monitor the live NSE filings, AI sentiments, and trade executions directly from your Mac terminal without manual SSH:

### 1. Filtered News Stream (Filings, AI Decisions & Orders Only)
```bash
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sudo docker logs -f nse_catalyst_terminal | grep --line-buffered -v -E '\"GET |\"POST |INFO:uvicorn'"
```

### 2. Full Real-Time Log Stream
```bash
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sudo docker logs -f nse_catalyst_terminal"
```

### 3. Recent Log Snapshot (Last 50 Lines)
```bash
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sudo docker logs --tail 50 nse_catalyst_terminal"
```

### 4. Container Status & Resource Usage
```bash
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sudo docker ps && sudo docker stats --no-stream"
```

### 5. Inspect SQLite Database on Remote VM
```bash
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sqlite3 /opt/nse_trading_terminal/data/strategy.db 'SELECT id, symbol, published_at, category, conviction, action FROM trade_executions ORDER BY id DESC LIMIT 10;'"
```

---

## ⏰ Automated Market Hours Scheduling

To automatically start the VM before market open and stop after market close:

In `infra/gcp/terraform.tfvars`:
```hcl
enable_schedule   = true
schedule_timezone = "Asia/Kolkata"
schedule_start    = "00 09 * * 1-5"   # 09:00 AM IST Mon-Fri
schedule_stop     = "45 15 * * 1-5"   # 03:45 PM IST Mon-Fri
```
Apply changes:
```bash
cd infra/gcp && terraform apply
```

---

## 🛑 Destroying Infrastructure (Tear Down)

To tear down all GCP resources and release the static IP:
```bash
cd infra/gcp && terraform destroy
```

