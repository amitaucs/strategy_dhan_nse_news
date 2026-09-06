# 🌐 Common GCP Host Infrastructure (Terraform)

This directory contains the single source of truth for **Shared Host Infrastructure** across all trading strategies running on Google Cloud Platform.

---

## 🏛️ Architecture & Shared Resources

* **GCP Compute Engine Host VM**: `nse-trading-terminal` (`e2-micro`, Always Free Tier in `us-central1` or Mumbai `asia-south1`).
* **Static External IP**: Dedicated static IP attached to the VM.
* **Shared Network Firewall**: Exposes SSH (`22`) and strategy Web UI ports (`8000`, `8015`, etc.).
* **Automated Market Hours Scheduler**: Optionally starts VM before 09:00 AM IST and stops after 03:45 PM IST Mon-Fri.

---

## 📁 Files in This Directory

* **`terraform_common.tfvars.example`**: Template for shared GCP project, region, and host VM settings.
* **`terraform_common.tfvars`**: Your active shared settings (ignored by Git for secret protection).

---

## ⚙️ How Strategies Inherit Common Variables

When provisioning infrastructure or deploying code from any strategy, the strategy deployment scripts automatically merge:
1. `infra/terraform/terraform_common.tfvars` (Common Host)
2. `strategies/<strategy>/infra/gcp/terraform.tfvars` (Strategy Specific)

```bash
# Example Terraform command executed by ./infra/scripts/deploy.sh:
terraform apply \
  -var-file="../../infra/terraform/terraform_common.tfvars" \
  -var-file="terraform.tfvars"
```

