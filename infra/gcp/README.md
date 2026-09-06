# Google Cloud Platform (GCP) Infrastructure (Terraform)

This directory contains Terraform infrastructure as code (IaC) to provision and run the **NSE Catalyst Trading Terminal** on Google Cloud Platform.

---

## Architecture & Features

- **Default Setting (Option 1 - Always Free Tier)**:
  - **Region**: `us-central1` (Iowa) / `us-central1-a`
  - **Machine Type**: `e2-micro` (2 vCPUs shared, 1 GB RAM)
  - **Disk**: 30 GB standard persistent disk (`pd-standard`)
  - **Monthly Cost**: **₹0 / month (100% Free Forever under GCP Always Free Tier)**
- **Configurable Region (e.g. Option 2 - Mumbai)**:
  - Can be switched to `asia-south1` (Mumbai) by changing one line in `terraform.tfvars`.
- **Static External IP**: Ensures your web URL and DNS never change when the VM restarts.
- **Automated Docker Bootstrap**: Startup script automatically installs Docker Engine and Docker Compose V2 on the VM.
- **Firewall Rules**: Automatically allows inbound traffic on port `8000` (Web UI) and port `22` (SSH).

---

## Prerequisites

1. **Google Cloud SDK (`gcloud`)**:
   ```bash
   # Install via Homebrew on Mac:
   brew install google-cloud-sdk
   ```
2. **Terraform**:
   ```bash
   brew install terraform
   ```
3. **Authenticate with GCP**:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project YOUR_GCP_PROJECT_ID
   ```

---

## Quick Start (Automated 1-Click Deployment)

From the project root:

```bash
# 1. Copy variables file & set your project ID:
cp infra/gcp/terraform.tfvars.example infra/gcp/terraform.tfvars

# 2. Edit infra/gcp/terraform.tfvars:
#    project_id = "your-actual-gcp-project-id"

# 3. Run the automated deployment script:
./infra/gcp/deploy.sh
```

The script will:
1. Provision the GCE VM, static IP, and firewall rules with Terraform.
2. Wait for Docker initialization.
3. Securely sync your code and `.env` to the remote VM.
4. Launch the Docker container in the background.
5. Print your live Web UI URL (e.g. `http://34.x.x.x:8000`).

---

## Manual Step-by-Step Deployment with Terraform

If you prefer running Terraform commands manually:

```bash
cd infra/gcp

# 1. Initialize Terraform
terraform init

# 2. Plan the deployment
terraform plan

# 3. Apply and provision infrastructure
terraform apply

# 4. View outputs (Public IP & Web URL)
terraform output
```

## Monitoring & Viewing Logs (Direct from Mac Terminal)

You can view, filter, and monitor the live NSE news feed and trade execution logs directly from your Mac terminal without having to manually log into the server.

### 1. Remote One-Liners (Run directly on your Mac)

#### 📡 Filtered News Stream (Announcements, AI Verdicts & Orders Only)
Displays only filtered-in catalysts, noise suppression reasons, AI verdicts, and trade triggers while stripping routine HTTP web requests:
```bash
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sudo docker logs -f nse_catalyst_terminal | grep --line-buffered -v -E '\"GET |\"POST |INFO:uvicorn'"
```


#### 📜 Full Real-Time Output Stream
Stream everything in real time (HTTP requests, radar polling cycles, database writes, and filings):
```bash
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sudo docker logs -f nse_catalyst_terminal"
```

#### 🔍 Recent Log Snapshot (Last 50 or 100 Lines)
Quickly inspect the most recent logs and return immediately to your terminal prompt:
```bash
# Last 50 lines:
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sudo docker logs --tail 50 nse_catalyst_terminal"

# Last 100 lines with timestamps:
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sudo docker logs --tail 100 -t nse_catalyst_terminal"
```

#### 🩺 Check Container Status & Resource Usage
```bash
# Container running status and uptime:
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sudo docker ps"

# Live CPU & RAM consumption:
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sudo docker stats --no-stream"
```

#### 🗄️ Inspect SQLite Database Records (Processed Filings & Trades)
```bash
# View last 10 trade signals recorded in SQLite:
gcloud compute ssh nse-trading-terminal --zone=us-central1-a --command="sqlite3 /opt/nse_trading_terminal/data/strategy.db 'SELECT id, symbol, published_at, category, conviction, action FROM trade_executions ORDER BY id DESC LIMIT 10;'"
```

---

### 2. Interactive SSH Session

If you prefer logging into the VM directly:

```bash
# 1. SSH into the GCP VM
gcloud compute ssh nse-trading-terminal --zone=us-central1-a

# 2. View logs inside the VM
sudo docker logs -f nse_catalyst_terminal

# Or filter news logs inside the VM (stripping HTTP web pings):
sudo docker logs -f nse_catalyst_terminal | grep --line-buffered -v -E '"GET |"POST |INFO:uvicorn'

# Or using the docker helper script:
cd /opt/nse_trading_terminal && sudo ./infra/docker/docker.sh logs
```

*(Press `Ctrl + C` at any time to exit live log streams).*

---

## How to Switch Between Free Tier (US) and Low-Latency (India)

Edit `infra/gcp/terraform.tfvars`:

### For 100% Free Tier (Default):
```hcl
region            = "us-central1"
zone              = "us-central1-a"
machine_type      = "e2-micro"
boot_disk_size_gb = 30
```

### For Mumbai Low Latency (~₹650 INR/month):
```hcl
region            = "asia-south1"
zone              = "asia-south1-a"
machine_type      = "e2-micro"
boot_disk_size_gb = 10
```

After modifying `terraform.tfvars`, run:
```bash
cd infra/gcp && terraform apply
```

---

## Automated Market Hours Scheduling (Start / Stop on Schedule)

You can configure GCP to automatically boot the VM before market open and shut it down after market close (e.g. 09:00 AM IST to 03:45 PM IST, Monday to Friday).

In `infra/gcp/terraform.tfvars`:
```hcl
enable_schedule   = true
schedule_timezone = "Asia/Kolkata"
schedule_start    = "00 09 * * 1-5"   # 09:00 AM IST Mon-Fri
schedule_stop     = "45 15 * * 1-5"   # 03:45 PM IST Mon-Fri
```

Run `cd infra/gcp && terraform apply`.

**Benefits**:
- **On Mumbai Region**: Reduces running hours by ~75%, cutting costs from ~₹650 down to **~₹150 / month**.
- **Container auto-starts**: When GCP powers on the VM, Docker automatically starts the trading terminal container.

---

## Destroying Infrastructure (Tear Down)

To completely delete all GCP resources and stop any billing:

```bash
cd infra/gcp
terraform destroy
```

