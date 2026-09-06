#!/usr/bin/env bash
# ==============================================================================
# Fast Code-Only Deployment Script for ST15_LargeCap on GCP VM
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
DEFAULT_REMOTE_DIR="/opt/st15_largecap"

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
BUNDLE_TMP="/tmp/st15_app_bundle.tar.gz"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT_ID="$2"; shift 2 ;;
    --zone) ZONE="$2"; shift 2 ;;
    --instance) INSTANCE_NAME="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--project <id>] [--zone <zone>] [--instance <name>]"
      exit 0
      ;;
    *)
      echo "❌ Unknown option: $1"
      exit 1
      ;;
  esac
done

echo "======================================================================"
echo "⚡ ST15_LargeCap — Fast Code Deploy to GCP VM"
echo "======================================================================"
echo "🖥️  Target VM:   ${INSTANCE_NAME} (Zone: ${ZONE}${PROJECT_ID:+, Project: $PROJECT_ID})"
echo "📁 Source:      ${PROJECT_ROOT}"
echo "📁 Destination: ${REMOTE_DIR}"
echo "======================================================================"

if ! command -v gcloud &> /dev/null; then
  echo "❌ Error: 'gcloud' CLI is not installed."
  exit 1
fi

echo ""
echo "📦 [1/4] Packaging ST15_LargeCap application files..."
cd "$PROJECT_ROOT"
rm -f "$BUNDLE_TMP"

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

echo "✅ Package created."

echo ""
echo "🚀 [2/4] Uploading archive to GCP VM..."
GCLOUD_PROJECT_FLAG=""
if [[ -n "$PROJECT_ID" ]]; then
  GCLOUD_PROJECT_FLAG="--project=$PROJECT_ID"
fi

gcloud compute scp "$BUNDLE_TMP" "${INSTANCE_NAME}:/tmp/st15_app_bundle.tar.gz" \
  --zone="$ZONE" $GCLOUD_PROJECT_FLAG

rm -f "$BUNDLE_TMP"
echo "✅ Package uploaded."

echo ""
echo "🔨 [3/4] Extracting code and launching Docker container on port 8015..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" $GCLOUD_PROJECT_FLAG --command="
  set -e
  sudo mkdir -p ${REMOTE_DIR}
  sudo tar -xzf /tmp/st15_app_bundle.tar.gz -C ${REMOTE_DIR}
  rm -f /tmp/st15_app_bundle.tar.gz
  cd ${REMOTE_DIR}
  sudo chmod +x infra/scripts/docker.sh
  sudo ./infra/scripts/docker.sh up -d --build
"

echo ""
echo "🩺 [4/4] Verifying container status..."
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" $GCLOUD_PROJECT_FLAG --command="
  sudo docker ps --filter 'name=st15_largecap_terminal'
"

echo "======================================================================"
echo "🎉 ST15_LargeCap deployment successfully finished on port 8015!"
echo "======================================================================"
