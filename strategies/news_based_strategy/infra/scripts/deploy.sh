#!/usr/bin/env bash
# ==============================================================================
# Automated Deployment Script for GCP Compute Engine
# Provisions infrastructure via Terraform, syncs codebase, and starts Docker.
# Usage:
#   ./infra/scripts/deploy.sh
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Resolve repository root
CUR="$PROJECT_ROOT"
while [[ "$CUR" != "/" && ! -d "$CUR/infra/terraform" ]]; do
  CUR="$(dirname "$CUR")"
done
REPO_ROOT="$CUR"

GCP_DIR="${PROJECT_ROOT}/infra/gcp"
COMMON_TFVARS="${REPO_ROOT}/infra/terraform/terraform_common.tfvars"
STRATEGY_TFVARS="${GCP_DIR}/terraform.tfvars"

cd "$GCP_DIR"

echo "======================================================================"
echo "⚡ NSE Catalyst Trading Terminal - GCP Terraform Deployment"
echo "======================================================================"

# Check if terraform is installed
if ! command -v terraform &> /dev/null; then
  echo "❌ Error: 'terraform' is not installed."
  echo "👉 Install Terraform via Homebrew: brew install terraform"
  exit 1
fi

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
  echo "❌ Error: 'gcloud' CLI is not installed."
  echo "👉 Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

# Check for terraform_common.tfvars
if [[ ! -f "$COMMON_TFVARS" ]]; then
  if [[ -f "${REPO_ROOT}/infra/terraform/terraform_common.tfvars.example" ]]; then
    echo "⚠️  'infra/terraform/terraform_common.tfvars' not found. Creating from example..."
    cp "${REPO_ROOT}/infra/terraform/terraform_common.tfvars.example" "$COMMON_TFVARS"
    echo "📝 Please edit 'infra/terraform/terraform_common.tfvars' with your GCP project_id and re-run:"
    echo "   ./infra/scripts/deploy.sh"
    exit 1
  fi
fi

# Check for strategy terraform.tfvars
if [[ ! -f "$STRATEGY_TFVARS" ]]; then
  if [[ -f "${GCP_DIR}/terraform.tfvars.example" ]]; then
    echo "⚠️  'infra/gcp/terraform.tfvars' not found. Creating from example..."
    cp "${GCP_DIR}/terraform.tfvars.example" "$STRATEGY_TFVARS"
  fi
fi

# 1. Terraform Init & Apply with merged variable files
echo "🔧 [1/4] Initializing and applying Terraform configuration..."
terraform init

VAR_ARGS=()
if [[ -f "$COMMON_TFVARS" ]]; then
  VAR_ARGS+=("-var-file=$COMMON_TFVARS")
fi
if [[ -f "$STRATEGY_TFVARS" ]]; then
  VAR_ARGS+=("-var-file=$STRATEGY_TFVARS")
fi

terraform apply -auto-approve "${VAR_ARGS[@]}"

# Extract outputs
INSTANCE_NAME=$(terraform output -raw instance_name)
EXTERNAL_IP=$(terraform output -raw instance_external_ip)
WEB_URL=$(terraform output -raw web_ui_url)
ZONE=$(grep -E '^\s*zone\s*=' "$COMMON_TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "us-central1-a")
PROJECT_ID=$(grep -E '^\s*project_id\s*=' "$COMMON_TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "")

echo ""
echo "🖥️  [2/4] Provisioned Instance: $INSTANCE_NAME ($EXTERNAL_IP in $ZONE)"

# 2. Wait for Docker installation on remote VM
echo "⏳ [3/4] Waiting for VM startup script & Docker service readiness..."
sleep 15
until gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" ${PROJECT_ID:+--project="$PROJECT_ID"} --command="which docker > /dev/null && docker info > /dev/null 2>&1 || sudo docker info > /dev/null 2>&1" -- -o StrictHostKeyChecking=no 2>/dev/null; do
  echo "   ... waiting for Docker to initialize on remote VM (takes ~30-45s on first boot)..."
  sleep 10
done

# 3. Sync codebase to remote instance
echo "📦 [4/4] Syncing codebase and launching container on remote VM..."
REMOTE_DIR="/opt/nse_trading_terminal"
if [[ -f "$STRATEGY_TFVARS" ]]; then
  STRAT_DIR=$(grep -E '^\s*remote_deploy_dir\s*=' "$STRATEGY_TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "")
  [[ -n "$STRAT_DIR" ]] && REMOTE_DIR="$STRAT_DIR"
fi

# Ensure remote user has write permissions
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" ${PROJECT_ID:+--project="$PROJECT_ID"} --command="sudo mkdir -p $REMOTE_DIR && sudo chown -R \$USER:\$USER $REMOTE_DIR"

# Copy project files (excluding .venv, git, database, and terraform cache)
cd "$PROJECT_ROOT"
tar \
  --exclude='.venv' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='data/*.db*' \
  --exclude='.terraform' \
  --exclude='*terraform*' \
  --exclude='*.log' \
  --exclude='.DS_Store' \
  -czf /tmp/nse_app_bundle.tar.gz .
gcloud compute scp /tmp/nse_app_bundle.tar.gz "${INSTANCE_NAME}:/tmp/nse_app_bundle.tar.gz" --zone="$ZONE" ${PROJECT_ID:+--project="$PROJECT_ID"}
rm -f /tmp/nse_app_bundle.tar.gz

gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" ${PROJECT_ID:+--project="$PROJECT_ID"} --command="
  cd $REMOTE_DIR
  tar -xzf /tmp/nse_app_bundle.tar.gz
  rm -f /tmp/nse_app_bundle.tar.gz
  chmod +x infra/scripts/docker.sh
  sudo ./infra/scripts/docker.sh up -d --build
"

echo ""
echo "======================================================================"
echo "🎉 Deployment Complete!"
echo "🌐 Web Dashboard: $WEB_URL"
echo "📜 View Live Logs: gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command=\"cd $REMOTE_DIR && sudo ./infra/scripts/docker.sh logs\""
echo "======================================================================"
