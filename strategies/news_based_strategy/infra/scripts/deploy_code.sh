#!/usr/bin/env bash
# ==============================================================================
# Fast Code-Only Deployment Script for GCP Compute Engine VM
# ==============================================================================
# Use this script to quickly push local code updates to the existing GCP VM
# and rebuild the Docker container without re-running Terraform / changing infra.
#
# Usage:
#   ./infra/scripts/deploy_code.sh
#   ./infra/scripts/deploy_code.sh --zone us-central1-a --instance nse-trading-terminal
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

COMMON_TFVARS="${REPO_ROOT}/infra/terraform/terraform_common.tfvars"
STRATEGY_TFVARS="${PROJECT_ROOT}/infra/gcp/terraform.tfvars"

# Default Configuration (parsed from common + strategy tfvars)
DEFAULT_PROJECT_ID=""
DEFAULT_ZONE="us-central1-a"
DEFAULT_INSTANCE="nse-trading-terminal"
DEFAULT_REMOTE_DIR="/opt/nse_trading_terminal"

if [[ -f "$COMMON_TFVARS" ]]; then
  COMMON_PID=$(grep -E '^\s*project_id\s*=' "$COMMON_TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "")
  COMMON_ZONE=$(grep -E '^\s*zone\s*=' "$COMMON_TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "")
  COMMON_INST=$(grep -E '^\s*instance_name\s*=' "$COMMON_TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "")
  [[ -n "$COMMON_PID" ]] && DEFAULT_PROJECT_ID="$COMMON_PID"
  [[ -n "$COMMON_ZONE" ]] && DEFAULT_ZONE="$COMMON_ZONE"
  [[ -n "$COMMON_INST" ]] && DEFAULT_INSTANCE="$COMMON_INST"
fi

if [[ -f "$STRATEGY_TFVARS" ]]; then
  STRAT_PID=$(grep -E '^\s*project_id\s*=' "$STRATEGY_TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "")
  STRAT_ZONE=$(grep -E '^\s*zone\s*=' "$STRATEGY_TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "")
  STRAT_INST=$(grep -E '^\s*instance_name\s*=' "$STRATEGY_TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "")
  STRAT_DIR=$(grep -E '^\s*remote_deploy_dir\s*=' "$STRATEGY_TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "")
  [[ -n "$STRAT_PID" ]] && DEFAULT_PROJECT_ID="$STRAT_PID"
  [[ -n "$STRAT_ZONE" ]] && DEFAULT_ZONE="$STRAT_ZONE"
  [[ -n "$STRAT_INST" ]] && DEFAULT_INSTANCE="$STRAT_INST"
  [[ -n "$STRAT_DIR" ]] && DEFAULT_REMOTE_DIR="$STRAT_DIR"
fi

PROJECT_ID="${PROJECT_ID:-$DEFAULT_PROJECT_ID}"
ZONE="${ZONE:-$DEFAULT_ZONE}"
INSTANCE_NAME="${INSTANCE_NAME:-$DEFAULT_INSTANCE}"
REMOTE_DIR="${REMOTE_DIR:-$DEFAULT_REMOTE_DIR}"
BUNDLE_TMP="/tmp/nse_app_bundle.tar.gz"

# Parse optional command line flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT_ID="$2"
      shift 2
      ;;
    --zone)
      ZONE="$2"
      shift 2
      ;;
    --instance)
      INSTANCE_NAME="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --project <id>       GCP Project ID (default: ${PROJECT_ID:-current active project})"
      echo "  --zone <zone>        GCP Compute Engine Zone (default: $ZONE)"
      echo "  --instance <name>    GCP VM Instance Name (default: $INSTANCE_NAME)"
      echo "  -h, --help           Show this help message"
      exit 0
      ;;
    *)
      echo "❌ Unknown option: $1"
      echo "Use $0 --help for usage details."
      exit 1
      ;;
  esac
done

echo "======================================================================"
echo "⚡ NSE Catalyst Trading Terminal — Fast Code Deploy to GCP"
echo "======================================================================"
echo "🖥️  Target VM:   ${INSTANCE_NAME} (Zone: ${ZONE}${PROJECT_ID:+, Project: $PROJECT_ID})"
echo "📁 Source:      ${PROJECT_ROOT}"
echo "📁 Destination: ${REMOTE_DIR}"
echo "======================================================================"

# 1. Verify gcloud is installed and authenticated
if ! command -v gcloud &> /dev/null; then
  echo "❌ Error: 'gcloud' CLI is not installed."
  echo "👉 Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

# 2. Package source code
echo ""
echo "📦 [1/4] Packaging application source files..."
cd "$PROJECT_ROOT"

# Clean any existing local bundle
rm -f "$BUNDLE_TMP"

# Create archive excluding virtualenvs, git, caches, DB files, and Terraform states
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
  -czf "$BUNDLE_TMP" .

BUNDLE_SIZE=$(du -h "$BUNDLE_TMP" | cut -f1)
echo "✅ Archive created ($BUNDLE_SIZE)."

# 3. Upload package to GCP VM
echo ""
echo "🚀 [2/4] Uploading archive to GCP VM via scp..."
GCLOUD_PROJECT_FLAG=""
if [[ -n "$PROJECT_ID" ]]; then
  GCLOUD_PROJECT_FLAG="--project=$PROJECT_ID"
fi

gcloud compute scp "$BUNDLE_TMP" "${INSTANCE_NAME}:/tmp/nse_app_bundle.tar.gz" \
  --zone="$ZONE" $GCLOUD_PROJECT_FLAG

rm -f "$BUNDLE_TMP"
echo "✅ Package uploaded to VM."

# 4. Extract and rebuild container on VM
echo ""
echo "🔨 [3/4] Extracting code and rebuilding Docker container on VM..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" $GCLOUD_PROJECT_FLAG --command="
  set -e
  sudo mkdir -p ${REMOTE_DIR}
  sudo tar -xzf /tmp/nse_app_bundle.tar.gz -C ${REMOTE_DIR}
  rm -f /tmp/nse_app_bundle.tar.gz
  cd ${REMOTE_DIR}
  sudo chmod +x infra/scripts/docker.sh
  sudo ./infra/scripts/docker.sh up -d --build
"

# 5. Verify container health & status
echo ""
echo "🩺 [4/4] Verifying live container health..."
sleep 3
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" $GCLOUD_PROJECT_FLAG --command="
  sudo docker ps --filter 'name=nse_catalyst_terminal'
  echo ''
  echo '📡 Status Telemetry Check:'
  curl -s http://localhost:8000/api/status | grep -o '\"dry_run\":[^,]*' || true
  curl -s http://localhost:8000/api/status | grep -o '\"auto_order\":[^,]*' || true
  curl -s http://localhost:8000/api/status | grep -o '\"expiry_message\":[^,]*' || true
  curl -s http://localhost:8000/api/status | grep -o '\"trade_cutoff_time\":[^,]*' || true
  curl -s http://localhost:8000/api/status | grep -o '\"square_off_time\":[^,]*' || true
"

echo ""
echo "======================================================================"
echo "🎉 Code deployment successfully finished!"
echo "🌐 Terminal Dashboard: https://stnse.amitdatta.co.in"
echo "📜 View live logs:     gcloud compute ssh $INSTANCE_NAME --zone=$ZONE $GCLOUD_PROJECT_FLAG --command=\"cd $REMOTE_DIR && sudo ./infra/scripts/docker.sh logs\""
echo "======================================================================"
