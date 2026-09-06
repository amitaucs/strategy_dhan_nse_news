#!/usr/bin/env bash
# ==============================================================================
# Fast Code-Only Deployment Script for GCP Compute Engine VM
# ==============================================================================
# Use this script to quickly push local code updates to the existing GCP VM
# and rebuild the Docker container without re-running Terraform / changing infra.
#
# Usage:
#   ./deploy_code.sh
#   ./infra/gcp/deploy_code.sh
#   ./infra/gcp/deploy_code.sh --zone us-central1-a --instance nse-trading-terminal
# ==============================================================================

set -e

# Resolve script directory even when executed via symlink
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
if [[ -f "${SCRIPT_DIR}/pyproject.toml" || -d "${SCRIPT_DIR}/src/news_based_strategy" ]]; then
  PROJECT_ROOT="$SCRIPT_DIR"
  GCP_DIR="${SCRIPT_DIR}/infra/gcp"
elif [[ -f "${SCRIPT_DIR}/../../pyproject.toml" || -d "${SCRIPT_DIR}/../../src/news_based_strategy" ]]; then
  PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  GCP_DIR="$SCRIPT_DIR"
else
  PROJECT_ROOT="$SCRIPT_DIR"
  GCP_DIR="${SCRIPT_DIR}/infra/gcp"
fi

# Default Configuration (parsed from terraform.tfvars if available)
TFVARS="${GCP_DIR}/terraform.tfvars"
if [[ -f "$TFVARS" ]]; then
  DEFAULT_PROJECT_ID=$(grep -E '^\s*project_id\s*=' "$TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "")
  DEFAULT_ZONE=$(grep -E '^\s*zone\s*=' "$TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "us-central1-a")
  DEFAULT_INSTANCE=$(grep -E '^\s*instance_name\s*=' "$TFVARS" | head -n1 | cut -d'=' -f2 | tr -d ' "' || echo "nse-trading-terminal")
else
  DEFAULT_PROJECT_ID=""
  DEFAULT_ZONE="us-central1-a"
  DEFAULT_INSTANCE="nse-trading-terminal"
fi

PROJECT_ID="${PROJECT_ID:-$DEFAULT_PROJECT_ID}"
ZONE="${ZONE:-$DEFAULT_ZONE}"
INSTANCE_NAME="${INSTANCE_NAME:-$DEFAULT_INSTANCE}"
REMOTE_DIR="/opt/nse_trading_terminal"
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
  sudo chmod +x infra/docker/docker.sh
  sudo ./infra/docker/docker.sh up -d --build
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
echo "📜 View live logs:     gcloud compute ssh $INSTANCE_NAME --zone=$ZONE $GCLOUD_PROJECT_FLAG --command=\"cd $REMOTE_DIR && sudo ./infra/docker/docker.sh logs\""
echo "======================================================================"
